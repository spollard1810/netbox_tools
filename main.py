import pynetbox
import csv
import os
import sys
import warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from collections import defaultdict
import time # For timing operations

# --- Configuration ---
NETBOX_URL = os.getenv('NETBOX_URL')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN')
OUTPUT_CSV_FILE = "netbox_all_interfaces_ips_client_filtered.csv"
IGNORE_SSL_ERRORS = os.getenv('NETBOX_IGNORE_SSL', 'false').lower() == 'true'
VERBOSE_LOGGING = os.getenv('VERBOSE_LOGGING', 'true').lower() == 'true' # Control verbosity

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
        print("Initiating fetch for ALL DCIM interfaces (pynetbox will fetch pages as needed)...")
        start_time_fetch_interfaces = time.time()
        all_dcim_interfaces_iterable = nb.dcim.interfaces.all()
        # Note: The actual API calls for pages happen when we iterate below.
        # The .all() call itself is quick as it just sets up the iterator.
        
        virtual_interfaces_map = {}
        print("Starting to iterate through all interfaces to filter virtual ones and build a map...")
        count_total_interfaces_scanned = 0
        count_virtual_interfaces_identified = 0
        
        # For more detailed progress, let's get the total count first (if possible and not too slow)
        # This makes an extra call to get the count, but helps with % progress.
        # It might be slow itself if NetBox struggles to count all interfaces.
        estimated_total_interfaces = 0
        try:
            print("Attempting to get total count of DCIM interfaces for progress reporting...")
            estimated_total_interfaces = all_dcim_interfaces_iterable.count # This triggers a limit=1 API call
            print(f"Estimated total DCIM interfaces to scan: {estimated_total_interfaces}")
        except Exception as e:
            print(f"Warning: Could not get total interface count upfront: {e}. Progress will be based on scanned items.")

        start_time_filter_interfaces = time.time()

        for iface in all_dcim_interfaces_iterable: # This is where pynetbox fetches pages
            count_total_interfaces_scanned += 1
            
            if count_total_interfaces_scanned % 1000 == 0: # Adjust frequency of detailed log
                elapsed_filtering_time = time.time() - start_time_filter_interfaces
                progress_msg = f"  Scanned {count_total_interfaces_scanned}"
                if estimated_total_interfaces > 0:
                    progress_percent = (count_total_interfaces_scanned / estimated_total_interfaces) * 100
                    progress_msg += f"/{estimated_total_interfaces} ({progress_percent:.2f}%)"
                progress_msg += f" interfaces. Found {count_virtual_interfaces_identified} virtual so far. (Filtering time: {elapsed_filtering_time:.2f}s)"
                print(progress_msg)
            elif VERBOSE_LOGGING and count_total_interfaces_scanned % 100 == 0 : # More frequent, less detailed log
                 print(f"  Processed interface #{count_total_interfaces_scanned}...")


            is_interface_virtual = False
            interface_kind_val = "N/A"
            interface_type_val = "N/A"

            if hasattr(iface, 'kind') and iface.kind and hasattr(iface.kind, 'value'):
                interface_kind_val = iface.kind.value
                if interface_kind_val == 'virtual':
                    is_interface_virtual = True
            
            if not is_interface_virtual and hasattr(iface, 'type') and iface.type and hasattr(iface.type, 'value'):
                interface_type_val = iface.type.value
                if interface_type_val == 'virtual': # Primarily for older NetBox
                    is_interface_virtual = True
                # elif interface_type_val in ['lag', 'bridge']: # Consider if needed for older NetBox
                #     is_interface_virtual = True

            if VERBOSE_LOGGING and count_total_interfaces_scanned % 500 == 0 : # Log details for some interfaces
                if hasattr(iface, 'name'):
                    print(f"    Detail: Interface ID {iface.id} Name: {iface.name}, Kind: {interface_kind_val}, Type: {interface_type_val}, IsVirtual: {is_interface_virtual}")
                else:
                    print(f"    Detail: Interface ID {iface.id} (No name), Kind: {interface_kind_val}, Type: {interface_type_val}, IsVirtual: {is_interface_virtual}")


            if is_interface_virtual:
                if iface.device and hasattr(iface.device, 'name') and hasattr(iface, 'name'):
                    virtual_interfaces_map[iface.id] = {
                        'name': iface.name,
                        'device_name': iface.device.name
                    }
                    count_virtual_interfaces_identified += 1
                    if VERBOSE_LOGGING and count_virtual_interfaces_identified % 100 == 0:
                         print(f"      Added virtual interface: {iface.name} on {iface.device.name} (Total virtual: {count_virtual_interfaces_identified})")
                # else:
                    # if VERBOSE_LOGGING:
                    #     if hasattr(iface, 'name'):
                    #         print(f"    Skipping virtual interface {iface.name} (ID: {iface.id}) due to missing device/name.")
                    #     else:
                    #         print(f"    Skipping virtual interface (ID: {iface.id}, no name) due to missing device/name.")
        
        end_time_filter_interfaces = time.time()
        print(f"Finished scanning and filtering interfaces. Total scanned: {count_total_interfaces_scanned}.")
        print(f"Identified {count_virtual_interfaces_identified} virtual interfaces with devices.")
        print(f"Time taken for fetching/filtering interfaces: {end_time_filter_interfaces - start_time_fetch_interfaces:.2f}s (Filtering part: {end_time_filter_interfaces - start_time_filter_interfaces:.2f}s)")


        if not virtual_interfaces_map:
            print("No virtual interfaces found matching criteria. Exiting.")
            # ... (rest of the code for creating empty CSV)
            return

        # ... (rest of the script: fetching IPs, combining, writing CSV) ...
        # Consider adding similar verbose logging to the IP fetching loop if needed

        # 2. Fetch ALL IP Addresses
        print("\nInitiating fetch for ALL IPAM IP addresses...")
        start_time_fetch_ips = time.time()
        all_ip_addresses_iterable = nb.ipam.ip_addresses.all()
        
        interface_to_ips_map = defaultdict(list)
        
        count_total_ips_scanned = 0
        count_ips_mapped_to_virtual_iface = 0
        
        estimated_total_ips = 0
        try:
            print("Attempting to get total count of IPAM IP addresses for progress reporting...")
            estimated_total_ips = all_ip_addresses_iterable.count
            print(f"Estimated total IP addresses to scan: {estimated_total_ips}")
        except Exception as e:
            print(f"Warning: Could not get total IP count upfront: {e}. Progress will be based on scanned items.")

        print("Starting to iterate through all IP addresses to map them...")
        start_time_map_ips = time.time()

        for ip_obj in all_ip_addresses_iterable:
            count_total_ips_scanned +=1
            if count_total_ips_scanned % 10000 == 0: # Adjust frequency
                elapsed_mapping_time = time.time() - start_time_map_ips
                progress_msg = f"  Processed {count_total_ips_scanned}"
                if estimated_total_ips > 0:
                    progress_percent = (count_total_ips_scanned / estimated_total_ips) * 100
                    progress_msg += f"/{estimated_total_ips} ({progress_percent:.2f}%)"
                progress_msg += f" IP addresses. Mapped {count_ips_mapped_to_virtual_iface} to virtual interfaces. (Mapping time: {elapsed_mapping_time:.2f}s)"
                print(progress_msg)
            
            if ip_obj.assigned_object_type == 'dcim.interface' and ip_obj.assigned_object_id:
                interface_id = ip_obj.assigned_object_id
                if interface_id in virtual_interfaces_map:
                    interface_to_ips_map[interface_id].append(ip_obj.address)
                    count_ips_mapped_to_virtual_iface +=1
        
        end_time_map_ips = time.time()
        print(f"Finished processing IP addresses. Total scanned: {count_total_ips_scanned}.")
        print(f"Mapped {count_ips_mapped_to_virtual_iface} IPs to the identified virtual DCIM interfaces.")
        print(f"Time taken for fetching/mapping IPs: {end_time_map_ips - start_time_fetch_ips:.2f}s (Mapping part: {end_time_map_ips - start_time_map_ips:.2f}s)")


        # 3. Combine the data
        print("\nCombining data and preparing CSV rows...")
        # ... (rest of combining and CSV writing) ...


    except pynetbox.core.query.RequestError as e:
        print(f"API Error during NetBox data fetching: {e}")
    except AttributeError as e:
        print(f"Attribute Error (check data structure or pynetbox version compatibility): {e}")
        import traceback
        traceback.print_exc()
    except MemoryError:
        print("Memory Error: The script ran out of memory. This can happen when loading very large datasets.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally: # Ensure CSV is written even if an error occurs after data collection
        if csv_data_rows: # Check if there's any data to write
            print("\nAttempting to write collected data to CSV (may be partial if error occurred mid-process)...")
            try:
                with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(header)
                    writer.writerows(csv_data_rows)
                if len(csv_data_rows) > 0:
                    print(f"Successfully wrote {len(csv_data_rows)} data rows to {OUTPUT_CSV_FILE}")
                else:
                    print(f"No data rows were populated to write to {OUTPUT_CSV_FILE}")
            except Exception as e_csv:
                print(f"Error writing to CSV: {e_csv}")
        elif not os.path.exists(OUTPUT_CSV_FILE): # If no data and file doesn't exist, create with header
            print(f"No data collected. Creating {OUTPUT_CSV_FILE} with headers only.")
            try:
                with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(header)
            except Exception as e_csv:
                print(f"Error writing header-only CSV: {e_csv}")


if __name__ == "__main__":
    main()