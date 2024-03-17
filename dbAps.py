import mysql.connector

def store_response_in_database(formatted_output):
    mydb = mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234567890.",
        database="aruba"
    )
    cursor = mydb.cursor()
    # Insert new data
    try:
        for network_info in formatted_output:
            sql = """INSERT INTO aps (Mac_Address, IP_Address, Mode, Clients, Type, Radio0_Channel, Radio0_Power, 
            Radio0_Utilization, Radio0_NoiseFloor, Radio1_Channel, Radio1_Power, Radio1_Utilization, Radio1_Noise_Floor)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            val = (
                network_info.get('Mac_Address'),
                network_info.get('IP_Address'),
                network_info.get('Mode'),
                network_info.get('Clients'),
                network_info.get('Type'),
                network_info.get('Radio0_Channel'),
                network_info.get('Radio0_Power'),
                network_info.get('Radio0_Utilization'),
                network_info.get('Radio0_NoiseFloor'),
                network_info.get('Radio1_Channel'),
                network_info.get('Radio1_Power'),
                network_info.get('Radio1_Utilization'),
                network_info.get('Radio1_Noise_Floor')
            )
            cursor.execute(sql, val)
            print(f"Inserted {cursor.rowcount} record(s).")

        mydb.commit()  # Commit the transaction
        print("Data stored in database successfully")
    except Exception as e:
        print("Error storing data in database:", e)
    cursor.close()
