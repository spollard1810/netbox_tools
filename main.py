import pynetbox
import csv
import os
import sys
import warnings # For SSL warning suppression
from urllib3.exceptions import InsecureRequestWarning # For SSL warning suppression

# --- Configuration ---
# Best practice: Use environment variables for sensitive data
NETBOX_URL = os.getenv('NETBOX_URL')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN')
OUTPUT_CSV_FILE = "netbox_virtual_interface_ips.csv"
# Set to True to ignore SSL certificate errors (e.g., for self-signed certs)
# WARNING: This is insecure for production environments.
IGNORE_SSL_ERRORS = os.getenv('NETBOX_IGNORE_SSL', 'false').lower() == 'true'


# --- Main Script ---
def main():
    if not NETBOX_URL or not NETBOX_TOKEN:
        print("Error: NETBOX_URL and NETBOX_TOKEN environment variables must be set.")
        print("Example: ")
        print("  export NETBOX_URL=\"https://netbox.example.com\"") # Note: HTTPS is typical
        print("  export NETBOX_TOKEN=\"your_api_token_here\"")
        print("  (Optional) export NETBOX_IGNORE_SSL=\"true\" # To ignore SSL cert errors")
        sys.exit(1)

    # Initialize NetBox API client
    try:
        nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

        if IGNORE_SSL_ERRORS:
            print("Warning: SSL certificate verification is disabled. This is insecure for production.")
            # Suppress only the single InsecureRequestWarning from urllib3 needed for self-signed certs
            warnings.simplefilter('ignore', InsecureRequestWarning)
            # Disable SSL verification on the underlying requests session
            nb.http_session.verify = False

        nb.status() # Test connection
        print(f"Successfully connected to NetBox API at {NETBOX_URL}")
    except pynetbox.core.query.RequestError as e:
        print(f"Error connecting to NetBox API: {e}")
        print("Please check NETBOX_URL, NETBOX_TOKEN, network connectivity, and SSL configuration if applicable.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during NetBox initialization: {e}")
        sys.exit(1)

    csv_data = []
    header = ['parent_hostname', 'ip_address', 'interface_name']
    csv_data.append(header)

    try:
        print("Fetching DCIM interfaces with 'virtual=True' flag...")
        dcim_virtual_interfaces = list(nb.dcim.interfaces.filter(virtual=True))

        if not dcim_virtual_interfaces:
            print("No DCIM interfaces found with the filter 'virtual=True'.")
        else:
            print(f"Found {len(dcim_virtual_interfaces)} DCIM interfaces marked as virtual.")

        processed_interfaces_count = 0
        for iface in dcim_virtual_interfaces:
            processed_interfaces_count += 1
            if processed_interfaces_count % 20 == 0 or processed_interfaces_count == len(dcim_virtual_interfaces):
                print(f"Processing interface {processed_interfaces_count}/{len(dcim_virtual_interfaces)}: {iface.name} (ID: {iface.id})...")

            interface_name = iface.name
            parent_hostname = "N/A"

            if iface.device and hasattr(iface.device, 'name'):
                parent_hostname = iface.device.name
            else:
                print(f"Warning: Interface '{interface_name}' (ID: {iface.id}) is not assigned to a device, or device has no name. Skipping IP lookup for it.")
                continue

            try:
                interface_id_for_filter = int(iface.id)
                assigned_ips = list(nb.ipam.ip_addresses.filter(interface_id=interface_id_for_filter))
            except ValueError:
                print(f"Error: Interface ID '{iface.id}' for interface '{interface_name}' is not a valid integer. Skipping.")
                continue
            except pynetbox.core.query.RequestError as e:
                print(f"Error fetching IPs for interface '{interface_name}' (ID: {iface.id}): {e}. Skipping this interface.")
                continue

            if not assigned_ips:
                # For CSV consistency, you might want to add an entry even if no IPs
                # csv_data.append([parent_hostname, "N/A", interface_name])
                # print(f"Info: Interface '{interface_name}' on '{parent_hostname}' has no assigned IP addresses.")
                pass
            else:
                for ip_address_obj in assigned_ips:
                    ip_addr_with_cidr = ip_address_obj.address
                    csv_data.append([parent_hostname, ip_addr_with_cidr, interface_name])

        if len(csv_data) <= 1 :
             print("No data collected. Either no matching virtual interfaces found, or they had no parent devices/IPs.")

        # Write data to CSV
        with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_data)

        if len(csv_data) > 1:
            print(f"\nSuccessfully wrote {len(csv_data) - 1} data rows to {OUTPUT_CSV_FILE}")
        else:
            print(f"\nNo data rows to write. {OUTPUT_CSV_FILE} contains only headers.")


    except pynetbox.core.query.RequestError as e:
        print(f"Error during NetBox data fetching: {e}")
    except AttributeError as e:
        print(f"Error accessing an attribute, possibly due to unexpected data structure from NetBox: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"An unexpected error occurred during data processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()