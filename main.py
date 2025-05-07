import pynetbox
import csv
import os
import sys
import warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from collections import defaultdict

# --- Configuration ---
NETBOX_URL = os.getenv('NETBOX_URL')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN')
OUTPUT_CSV_FILE = "netbox_all_interfaces_ips_client_filtered.csv"
IGNORE_SSL_ERRORS = os.getenv('NETBOX_IGNORE_SSL', 'false').lower() == 'true'

# --- Main Script ---
def main():
    if not NETBOX_URL or not NETBOX_TOKEN:
        print("Error: NETBOX_URL and NETBOX_TOKEN environment variables must be set.")
        sys.exit(1)

    try:
        nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
        if IGNORE_SSL_ERRORS:
            print("Warning: SSL certificate verification is disabled.")
            warnings.simplefilter('ignore', InsecureRequestWarning)
            nb.http_session.verify = False

        print("Testing NetBox API connection...")
        nb.status()
        print(f"Successfully connected to NetBox API at {NETBOX_URL}")

    except pynetbox.core.query.RequestError as e:
        print(f"Error connecting to NetBox API: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during NetBox initialization: {e}")
        sys.exit(1)

    csv_data_rows = []
    header = ['parent_hostname', 'ip_address', 'interface_name']

    try:
        # 1. Fetch ALL DCIM interfaces
        print("Fetching ALL DCIM interfaces (this may take time and memory)...")
        all_dcim_interfaces_iterable = nb.dcim.interfaces.all()
        
        virtual_interfaces_map = {}
        print("Filtering for virtual interfaces and building a map...")
        count_total_interfaces = 0
        count_virtual_interfaces_identified = 0
        for iface in all_dcim_interfaces_iterable:
            count_total_interfaces += 1
            if count_total_interfaces % 5000 == 0:
                print(f"  Scanned {count_total_interfaces} total interfaces...")
            
            # Determine if the interface is "virtual"
            is_interface_virtual = False
            if hasattr(iface, 'kind') and iface.kind and hasattr(iface.kind, 'value'):
                # NetBox >= 3.5: Use the 'kind' attribute
                if iface.kind.value == 'virtual':
                    is_interface_virtual = True
            elif hasattr(iface, 'type') and iface.type and hasattr(iface.type, 'value'):
                # Fallback for NetBox < 3.5 or if 'kind' is not present
                # This primarily targets interfaces explicitly typed as 'virtual'.
                if iface.type.value == 'virtual':
                    is_interface_virtual = True
                # To be more comprehensive for older NetBox versions and replicate a broader
                # `virtual=True` filter, you might need to include other types:
                # elif iface.type.value in ['lag', 'bridge']: # Add other types if needed
                # is_interface_virtual = True
            # else:
                # Edge case: Interface has no 'kind' and no 'type', or they are malformed.
                # print(f"Warning: Interface ID {iface.id} ({iface.name}) has no 'kind' or valid 'type' attribute.")


            if is_interface_virtual:
                if iface.device and hasattr(iface.device, 'name') and hasattr(iface, 'name'):
                    virtual_interfaces_map[iface.id] = {
                        'name': iface.name,
                        'device_name': iface.device.name
                    }
                    count_virtual_interfaces_identified += 1
        
        print(f"Finished scanning interfaces. Found {count_total_interfaces} total DCIM interfaces.")
        print(f"Identified {count_virtual_interfaces_identified} virtual interfaces with devices.")

        if not virtual_interfaces_map:
            print("No virtual interfaces found matching criteria. Exiting.")
            with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(header)
            print(f"{OUTPUT_CSV_FILE} created with headers only.")
            return

        # 2. Fetch ALL IP Addresses
        print("\nFetching ALL IPAM IP addresses (this may take time and memory)...")
        all_ip_addresses_iterable = nb.ipam.ip_addresses.all()
        interface_to_ips_map = defaultdict(list)
        
        count_total_ips = 0
        count_assigned_to_virtual_iface = 0
        print("Processing IP addresses and mapping them to interfaces...")
        for ip_obj in all_ip_addresses_iterable:
            count_total_ips +=1
            if count_total_ips % 10000 == 0:
                print(f"  Processed {count_total_ips} total IP addresses...")
            
            if ip_obj.assigned_object_type == 'dcim.interface' and ip_obj.assigned_object_id:
                interface_id = ip_obj.assigned_object_id
                if interface_id in virtual_interfaces_map: # Check if this IP belongs to one of our identified virtual interfaces
                    interface_to_ips_map[interface_id].append(ip_obj.address)
                    count_assigned_to_virtual_iface +=1
        
        print(f"Finished processing IP addresses. Found {count_total_ips} total IPs.")
        print(f"Mapped {count_assigned_to_virtual_iface} IPs to the identified virtual DCIM interfaces.")

        # 3. Combine the data
        print("\nCombining data and preparing CSV rows...")
        for iface_id, iface_data in virtual_interfaces_map.items():
            parent_hostname = iface_data['device_name']
            interface_name = iface_data['name']
            
            if iface_id in interface_to_ips_map:
                for ip_address_str in interface_to_ips_map[iface_id]:
                    csv_data_rows.append([parent_hostname, ip_address_str, interface_name])
            # else: # Include virtual interfaces even if they have no IPs
            #     csv_data_rows.append([parent_hostname, "N/A", interface_name])


        # 4. Write to CSV
        if not csv_data_rows:
            print("No data rows to write to CSV after filtering.")
            with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(header)
            print(f"{OUTPUT_CSV_FILE} created with headers only.")
        else:
            with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(header)
                writer.writerows(csv_data_rows)
            print(f"\nSuccessfully wrote {len(csv_data_rows)} data rows to {OUTPUT_CSV_FILE}")

    except pynetbox.core.query.RequestError as e:
        print(f"API Error during NetBox data fetching: {e}")
    except AttributeError as e:
        print(f"Attribute Error (check data structure or pynetbox version compatibility): {e}")
        import traceback
        traceback.print_exc()
    except MemoryError:
        print("Memory Error: The script ran out of memory. This can happen when loading very large datasets.")
        print("Consider reverting to the iterative approach for interfaces if memory is a constraint, or increase available memory.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()