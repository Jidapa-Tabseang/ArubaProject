from flask import Flask, jsonify
from flask_caching import Cache
import requests
from flask import request
from flask_mysqldb import MySQL
from flask_cors import CORS
import schedule
import time
import re
from dbAps import store_response_in_database
from dbNetwork import store_database
import mysql.connector
import threading 

ARUBA_API_ENDPOINT = 'https://172.31.98.1:4343/rest'
global iap_ip_addr
iap_ip_addr = '192.168.50.223'

app = Flask(__name__)
CORS(app)
cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 60})
mysql = MySQL(app)

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '1234567890.'
app.config['MYSQL_DB'] = 'aruba'

def login_aruba():
    # Extract credentials
    username = 'admin'
    password = '1234567890.'

    # Make a request to Aruba API for authentication
    aruba_api_url = 'https://172.31.98.1:4343/rest/login'
    headers = {'Content-Type': 'application/json'}
    payload = {'user': username, 'passwd': password}

    try:
        response = requests.post(aruba_api_url, headers=headers, json=payload, verify=False)

        if response.status_code == 200:
            aruba_response = response.json()
            sid = aruba_response.get("sid")
            return sid
        else:
            print('Authentication failed')
            return None
    except requests.exceptions.RequestException as e:
        print(f'Error: {str(e)}')
        return None

def get_network(iap_ip_addr, sid):
    url = f"https://{iap_ip_addr}:4343/rest/show-cmd?iap_ip_addr={iap_ip_addr}&cmd=show%20aps&sid={sid}" #aps
    response = requests.get(url, verify=False)  # In case the SSL Certificate is not actually used or the SSL Certificate is invalid.
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to fetch network info:", response.status_code)
        return None
def parse_ap_data_cached(command_output):
    ap_list = []
    ap_rows = command_output.split('\n')[7:-1]  # Exclude header and empty lines
    for row in ap_rows:
        if '------------------' not in row:  # Skip rows with dashes
            columns = row.split()
            ap_info = {
                "Mac_Address": columns[0],
                "IP_Address": columns[1],
                "Mode": columns[2],
                "Clients": int(columns[4]) if columns[4] != '-------' else None,
                "Type": columns[5],
                "Radio0_Channel": columns[10],
                "Radio0_Power": int(columns[11]) if columns[11] != '------------------' else None,
                "Radio0_Utilization": int(columns[12].split('(')[0]) if columns[12] != '------------------' else None,
                "Radio0_NoiseFloor": int(columns[13].split('(')[0]) if columns[13] != '------------------' else None,
                "Radio1_Channel": columns[14],
                "Radio1_Power": int(columns[15]) if columns[15] != '------------------' else None,
                "Radio1_Utilization": int(columns[16].split('(')[0]) if columns[16] != '------------------' else None,
                "Radio1_Noise_Floor": int(columns[17].split('(')[0]) if columns[17] != '------------------' else None,

            }
            ap_list.append(ap_info)
    return ap_list
def update_database():
    sid = login_aruba()
    if sid:
        network = get_network(iap_ip_addr, sid)
        if network and "Command output" in network:
            command_output = network["Command output"]
            ap_list = parse_ap_data_cached(command_output)
            store_response_in_database(ap_list)
        else:
            print("Failed to get network data.")
    else:
        print("Failed to authenticate.")

#Data extracted from db
@app.route('/AccessPoints', methods=['GET'])
def get_latest_access_points_data():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT aps.Mac_Address, aps.IP_Address, aps.Mode, aps.Clients, aps.Type, 
               aps.Radio0_Channel, aps.Radio0_Power, aps.Radio0_Utilization, 
               aps.Radio0_NoiseFloor, aps.Radio1_Channel, aps.Radio1_Power, 
               aps.Radio1_Utilization, aps.Radio1_Noise_Floor
        FROM aps
        WHERE aps.Time = (
            SELECT MAX(Time) 
            FROM aps 
        );
    """)
    data = cur.fetchall()
    cur.close()
    
    result = []
    for row in data:
        result.append({
            'Mac_Address': row[0],
            'IP_Address': row[1],
            'Mode': row[2],
            'Clients': row[3],
            'Type': row[4],
            'Radio0_Channel': row[5],
            'Radio0_Power': row[6],
            'Radio0_Utilization': row[7],
            'Radio0_NoiseFloor': row[8],
            'Radio1_Channel': row[9],
            'Radio1_Power': row[10],
            'Radio1_Utilization': row[11],
            'Radio1_Noise_Floor': row[12]
        })
    
    return jsonify(result)

#count of aps up down 
def count_unique_aps():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT Mac_Address) AS AccessPoints FROM aps;
    """)
    data = cur.fetchone()
    cur.close()
    return data[0] if data else 0

@app.route('/count-aps', methods=['GET'])
def count_aps():
    cur = mysql.connection.cursor()

    # Retrieve all Mac Addresses from keymac table
    cur.execute("""
        SELECT DISTINCT Mac_Address
        FROM keymac;
    """)
    keymac_data = cur.fetchall()
    keymac_set = set(row[0] for row in keymac_data)
    # Retrieve the MAC Address available in the aps table and match it in the keymac table using the latest time from the aps table.
    cur.execute("""
        SELECT DISTINCT Mac_Address
        FROM aps
        WHERE Time = (SELECT MAX(Time) FROM aps)
        AND Mac_Address IN %s;
    """, (tuple(keymac_set),))
    aps_data = cur.fetchall()
    aps_set = set(row[0] for row in aps_data)

    cur.close()
    # Count the number of Mac Addresses that are not in the keymac table and are present in the aps table at the latest time.
    num_down = len(keymac_set - aps_set)
    # Count the number of MAC Addresses that exist in the aps table and match them in the keymac table.
    num_up = len(aps_set)

    return jsonify({"up": num_up, "down": num_down})


@app.route('/insertlocation', methods=['POST'])
def insert_access_point():
    try:
        data = request.get_json()

        # Extract data from the JSON payload
        lat = data.get('lat')
        lng = data.get('lng')
        mac_address = data.get('Mac_Address')
        location = data.get('location')

        # Save data to MySQL database
        save_data_to_db(lat, lng, mac_address, location)

        return jsonify({'message': 'Data successfully inserted into the database'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def save_data_to_db(lat, lng, mac_address, location):
    cursor = mysql.connection.cursor()
    sql = "INSERT INTO keymac (lat, lng, Mac_Address, location) VALUES (%s, %s, %s, %s)"
    values = (lat, lng, mac_address, location)

    cursor.execute(sql, values)
    mysql.connection.commit() 
    cursor.close()

@app.route('/deletelocation', methods=['DELETE'])
def delete_access_point():
    try:
        data = request.get_json()

        # Extract data from the JSON payload
        mac_address = data.get('Mac_Address')

        # Delete data from MySQL database
        delete_data_from_db(mac_address)

        return jsonify({'message': 'Data successfully deleted from the database'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def delete_data_from_db(mac_address):
    cursor = mysql.connection.cursor()
    sql = "DELETE FROM keymac WHERE Mac_Address = %s"
    value = (mac_address,)

    cursor.execute(sql, value)
    mysql.connection.commit()
    cursor.close()

@app.route('/accesspoint-locations', methods=['GET'])
def get_accesspoint_locations():
    cur = mysql.connection.cursor()
    cur.execute("SELECT `Mac_Address`, `Location`, `lat`, `lng` FROM `keymac`")
    data = cur.fetchall()
    cur.close()
    accesspoint_locations = [{'Mac_Address': row[0], 'location': row[1], 'lat': row[2], 'lng': row[3]} for row in data]
    return jsonify(accesspoint_locations)

def get_network_NW(iap_ip_addr, sid):
    url = f"https://{iap_ip_addr}:4343/rest/show-cmd?iap_ip_addr={iap_ip_addr}&cmd=show%20network&sid={sid}" #Netwotk
    response = requests.get(url, verify=False)  
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to fetch network info:", response.status_code)
        return None
    
@app.route('/network', methods=['GET']) # when you want to see data of network
def get_network_route_NW():
    sid = login_aruba()
    if sid:
        network = get_network_NW(iap_ip_addr, sid)  # Pass the iap_ip_addr and sid values into the function get_network()
        if network and "Command output" in network:
            command_output = network["Command output"]
            lines = command_output.split("\n")
            headers = lines[5].split()
            data_lines = lines[7:]
            
            formatted_output = []
            for line in data_lines:
                data = line.split()
                if len(data) >= 13 and data[2].isdigit():  # Ensure that the line has enough data points and the third column is a digit
                    network_info = {
                        "Profile Name": data[0],
                        "ESSID": data[1],
                        "Clients": int(data[2]),
                        "Type": data[3],
                        "Band": data[4],
                        "Key Management": data[6],
                        "IP Assignment": data[7],
                        "Status": data[9],
                        "Active": data[12],
                    }
                    formatted_output.append(network_info)
            return jsonify(formatted_output)
        else:
            return jsonify({"error": "Failed to get network data."})
    else:
        return jsonify({"error": "Failed to authenticate."})

    
@app.route('/networkCount', methods=['GET'])
def get_network_count():
    sid = login_aruba()
    total_network_count = 0
    if sid:
        network = get_network_NW(iap_ip_addr, sid)  # ส่ง sid มาให้ฟังก์ชัน get_network()
        if network and "Command output" in network:
            command_output = network["Command output"]
            lines = command_output.split("\n")
            data_lines = lines[7:]
            
            for line in data_lines:
                data = line.split()
                if len(data) >= 13 and data[2].isdigit():  # Ensure that the line has enough data points and the third column is a digit
                    total_network_count += 1

            return jsonify({"networkData": total_network_count})
        else:
            return jsonify({"error": "Failed to get network data."})
    else:
        return jsonify({"error": "Failed to authenticate."})

def get_network_Client(iap_ip_addr, sid):
    url = f"https://{iap_ip_addr}:4343/rest/show-cmd?iap_ip_addr={iap_ip_addr}&cmd=show%20clients&sid={sid}" #Clients
    response = requests.get(url, verify=False)  # ในกรณีที่ไม่ได้ใช้ SSL Certificate จริง ๆ หรือ SSL Certificate ไม่ถูกต้อง
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to fetch network info:", response.status_code)
        return None

@app.route('/Clients', methods=['GET']) # when you wnat to see data of clients but not JSON file
def get_network_route_Client():
    sid = login_aruba()
    if sid:
        network = get_network_Client(iap_ip_addr, sid)  # ส่งค่า iap_ip_addr และ sid เข้าไปในฟังก์ชัน get_network()
        if network and "Command output" in network:
            return jsonify(network)
        else:
            return jsonify({"error": "Failed to get network data."})
    else:
        return jsonify({"error": "Failed to authenticate."})
    
def count_ip_addresses(data):
    if data and "Command output" in data:
        command_output = data["Command output"]
        ip_addresses = re.findall(r'\d+\.\d+\.\d+\.\d+', command_output)  # Use regex to find IP addresses
        return len(ip_addresses)
    else:
        print("No valid data found.")
        return 0

@app.route('/countClients', methods=['GET'])
def get_network_clients_CC():
    sid = login_aruba()
    if sid:
        network_data = get_network_Client(iap_ip_addr, sid)

        if network_data and "Command output" in network_data:
            command_output = network_data["Command output"]
            ip_count = count_ip_addresses(network_data)
            lines = command_output.split("\n")
            headers = lines[5].split()
            data_lines = lines[7:]
            
            formatted_output = []
            for line in data_lines:
                data = line.split()
                if len(data) >= 13 and data[2].isdigit():
                    network_info = {
                        "Profile Name": data[0],
                        "ESSID": data[1],
                        "Clients": int(data[2]),
                        "Type": data[3],
                        "Band": data[4],
                        "Key Management": data[6],
                        "IP Assignment": data[7],
                        "Status": data[9],
                        "Active": data[12],
                    }
                    formatted_output.append(network_info)

            return jsonify({"clientsData": ip_count})
        else:
            return jsonify({"error": "Failed to get network data."})
    else:
        return jsonify({"error": "Failed to authenticate."})

def calculate_average_speed(client_data):
    total_speed = 0
    total_clients = 0
    lines = client_data.split('\n')

    for line in lines[2:]:
        columns = line.split()
        if columns:
            try:
                speed = float(columns[-1].replace('(', '').replace(')', '').replace('good', '').replace('bad', '').replace('average', ''))
                total_speed += speed
                total_clients += 1
            except ValueError:
                continue
    if total_clients > 0:
        average_speed = total_speed / total_clients
        return average_speed
    else:
        return 0
def get_client_speed(sid):
    url = f"{ARUBA_API_ENDPOINT}/show-cmd"
    params = {'iap_ip_addr': iap_ip_addr, 'cmd': 'show clients', 'sid': sid}

    try:
        response = requests.get(url, params=params, verify=False)
        if response.status_code == 200:
            ap_data = response.json()
            if "Command output" in ap_data:
                command_output = ap_data["Command output"]
                average_speed = calculate_average_speed(command_output)
                rounded_average_speed = round(average_speed, 2)
                return rounded_average_speed
        else:
            print(f'การดึงข้อมูลล้มเหลว รหัสสถานะ: {response.status_code}')
    except requests.exceptions.RequestException as e:
        print(f'ข้อผิดพลาด: {str(e)}')
    return None

@app.route('/speed', methods=['GET'])
def get_client_speed_route_Sp():
    sid = login_aruba()
    if sid:
        speed = get_client_speed(sid)
        if speed is not None:
            return jsonify({"speedData": speed})
        else:
            return jsonify({"error": "Failed to get client speed."})
    else:
        return jsonify({"error": "Failed to authenticate."})

def update_database_periodically():
    update_database()

def run_schedule_and_flask():
    schedule.every(1).minute.do(update_database_periodically) 
    update_database_periodically() 
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start a new thread to run the scheduling
schedule_thread = threading.Thread(target=run_schedule_and_flask)
schedule_thread.start()

# Start the Flask app
if __name__ == "__main__":
    # Run the Flask app
    app.run(debug=True, port=5009)
