import sqlite3
import logging

def cleanup_transfer_legs():
    """Remove transfer leg entries from the calls table"""
    try:
        conn = sqlite3.connect('radiance_md.db')
        cursor = conn.cursor()
        
        # Find transfer leg entries (calls to front desk number)
        front_desk_number = '+13132044895'
        
        # Get all calls to front desk
        cursor.execute('''
            SELECT call_control_id, caller_phone, called_phone, start_time, status 
            FROM calls 
            WHERE called_phone = ?
        ''', (front_desk_number,))
        
        transfer_legs = cursor.fetchall()
        print(f"Found {len(transfer_legs)} transfer leg entries:")
        
        for leg in transfer_legs:
            print(f"  - {leg[0]} (from {leg[1]} to {leg[2]}) - Status: {leg[4]}")
        
        if transfer_legs:
            # Delete transfer leg entries
            cursor.execute('DELETE FROM calls WHERE called_phone = ?', (front_desk_number,))
            deleted_count = cursor.rowcount
            conn.commit()
            print(f"✅ Deleted {deleted_count} transfer leg entries")
        else:
            print("ℹ️ No transfer leg entries found")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error cleaning up transfer legs: {str(e)}")

if __name__ == "__main__":
    cleanup_transfer_legs() 