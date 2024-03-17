import mysql.connector

mydb = mysql.connector.connect(
    host="localhost",
    user="root",
    password="1234567890.",
    database="aruba"
)

def store_database(formatted_output):
    cursor = mydb.cursor()

    for network_info in formatted_output:
        sql = """INSERT INTO network (Profile_Name, ESSId, Clients, Type, Band, Key_Management, IP_Assignment, Status, Active)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        val = (
            network_info.get('Profile Name'),
            network_info.get('ESSID'),
            network_info.get('Clients'),
            network_info.get('Type'),
            network_info.get('Band'),
            network_info.get('Key Management'),
            network_info.get('IP Assignment'),
            network_info.get('Status'),
            network_info.get('Active')
        )
        cursor.execute(sql, val)
        print(f"Inserted {cursor.rowcount} record(s).")

    mydb.commit()  # Commit the transaction

    cursor.close()
