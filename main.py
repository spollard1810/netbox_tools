import pynetbox
import csv
import os # For environment variables for better security

# --- Configuration ---
# Best practice: Use environment variables for sensitive data like tokens and URLs
NETBOX_URL = os.getenv('NETBOX_URL', "http://netbox.example.com") # Replace with your NetBox URL
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', "0123456789abcdef0123456789abcdef") # Replace with your NetBox API Token
OUTPUT_CSV_FILE = "netbox_virtual_interface_ips.csv"

# --- Main Script ---
def main():
    # Initialize NetBox API client
    try:
        nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
        # Optional: Disable SSL verification if using self-signed certs (not recommended for production)
        # nb.http_session.verify = False
        # import warnings
        # from requests.packages.urllib3.exceptions import InsecureRequestWarning
        # warnings.simplefilter('ignore', InsecureRequestWarning)

        # Test connection by fetching something simple (e.g., API status or a small list)
        nb.status() # Throws an exception if connection fails
        print(f"Successfully connected to NetBox API at {NETBOX_URL}")
    except pynetbox.core.query.RequestError as e:
        print(f"Error connecting to NetBox API: {e}")
        print("Please check NETBOX_URL and NETBOX_TOKEN.")
        return
    except Exception as e:
        print(f"An unexpected error occurred during NetBox initialization: {e}")
        return

    csv_data = []
    header = ['parent_hostname', 'ip_address', 'interface_name']
    csv_data.append(header)

    try:
        print("Fetching DCIM virtual interfaces...")
        # Filter for interfaces marked as virtual.
        # This typically includes loopbacks, VRF interfaces, etc., on physical devices.
        # If you meant interfaces on Virtual Machines, you'd query nb.virtualization.interfaces.all()
        # and access iface.virtual_machine.name
        virtual_interfaces = nb.dcim.interfaces.filter(virtual=True)
        # You could also filter by type, e.g., type__in=['lag', 'virtual', 'bridge']

        if not virtual_interfaces:
            print("No DCIM interfaces found with the filter 'virtual=True'.")
            # If you also want to consider LAGs as "virtual" (they often are logically)
            # lags = nb.dcim.interfaces.filter(type='lag')
            # virtual_interfaces = list(virtual_interfaces) + list(lags) # combine if needed

        processed_interfaces = 0
        for iface in virtual_interfaces:
            processed_interfaces += 1
            if processed_interfaces % 50 == 0:
                print(f"Processing interface {processed_interfaces}/{len(list(virtual_interfaces))}...")

            interface_name = iface.name
            parent_hostname = "N/A" # Default if no device

            if iface.device: # Check if the interface is assigned to a device
                parent_hostname = iface.device.name
            else:
                # This interface is not assigned to a device.
                # Depending on requirements, you might skip it or log it.
                print(f"Warning: Interface '{interface_name}' (ID: {iface.id}) is not assigned to a device. Skipping IP lookup for it.")
                # Optionally add a row indicating this:
                # csv_data.append([parent_hostname, "N/A", interface_name])
                continue # Skip to the next interface if no parent device

            # Fetch IP addresses assigned to this specific interface
            # The 'iface.ip_addresses' is a RelatedListManager, iterate it to get IPs
            ips_on_interface = list(iface.ip_addresses) # Convert to list to check if empty

            if not ips_on_interface:
                # If you want to list virtual interfaces even if they don't have IPs:
                # csv_data.append([parent_hostname, "N/A", interface_name])
                # print(f"Info: Interface '{interface_name}' on '{parent_hostname}' has no assigned IP addresses.")
                pass # Current behavior: only list interfaces with IPs
            else:
                for ip_address_obj in ips_on_interface:
                    # ip_address_obj.address usually includes the CIDR mask (e.g., "192.168.1.1/24")
                    ip_addr_with_cidr = ip_address_obj.address
                    csv_data.append([parent_hostname, ip_addr_with_cidr, interface_name])
                    print(f"  Found: Host: {parent_hostname}, IP: {ip_addr_with_cidr}, Interface: {interface_name}")

        if len(csv_data) <= 1 : # Only header is present
             print("No data collected. Either no matching virtual interfaces found, or they had no parent devices/IPs.")
             return

        # Write data to CSV
        with open(OUTPUT_CSV_FILE, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_data)
        print(f"\nSuccessfully wrote data to {OUTPUT_CSV_FILE}")

    except pynetbox.core.query.RequestError as e:
        print(f"Error during NetBox data fetching: {e}")
    except AttributeError as e:
        print(f"Error accessing an attribute, possibly due to unexpected data structure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during data processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()