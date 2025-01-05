import os
import csv
import json
import requests
import getpass
import sys
import re
import configparser
import argparse
import ast
from datetime import datetime, timedelta
from requests_toolbelt.multipart.encoder import MultipartEncoder

version = 20250105
print(f"INFO: Simple Classification Creator {version}")
help_message = '''
Optionally, you can set parameters:

   --default_user
        You can specify the username to use. if you do now specify one, it will look in the
        ~/.informatica_cdgc/credentials file (as shown below)
        Example:
            --default_user=shayes_compass

   --default_pwd
        You can specify the password to use. if you do now specify one, it will look in the
        ~/.informatica_cdgc/credentials file (as shown below)
        Example:
            --default_pwd=12345

   --default_pod
        You can specify the pod to use. if you do now specify one, it will look in the
        ~/.informatica_cdgc/credentials file (as shown below)
        Typically this "pod" can be shown in the url: for example: "dm-us"
        Example:
            --default_pwd=dm-us  

   --csv_file
        You can specify the config csv file to use directly, by setting it here. 
        It will default to the directory where the script/exe file resides.
        Example:
            --csv_file=my_classifications.csv

   --csv_file_path
         You can specify the config csv file to use directly, by setting it here. 
        Setting it with this option, will allow you to specify the full path (use linux forward slashes)
        Example:
            --csv_file_path=c:/junk/my_classifications.csv       

Direct Command line options:
   delete
        Use this command line argument to specify delete classifications action.

   extract
        Use this command to simply extract user created classifications. Use this to create 
        additional templates. The "details" that it downloads will provide the correct syntax for
        templates.

Python prerequisites:
    If needed, install the python prerequisites:  pip install requests argparse requests_toolbelt
    If executing using the Windows exe, all prerequisites should be covered.
    Ensure you have write access to the folder which the pythong script/binary resides

'''


default_pod="dmp-us"        
default_user=""
default_pwd=""


prompt_for_login_info = True
pause_before_loading = True
create_payloads_only = False
when_extracting_fetch_details = True
show_raw_errors = False
pause_at_end = True


# Paths
script_location = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
csv_file_path = script_location+'/xxxxxxxxxxxxxxxxxxxxx.csv'
csv_file = ''
templates_folder = script_location+'/templates'
extracts_folder = script_location+'/extracts'
current_classifications_file = "current_classifications.json"
current_classifications_details_file = "current_classifications_details.json"
current_lookup_file = "current_lookup_tables.json"
current_lookup_details_file = "current_lookup_table_details.json"
name_to_id_tokens = ["Classification Members"]

default_delete_csv_file = script_location+"/xxxxxxxxxxxxxxx.csv"

# Get the current timestamp for folder creation
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
payloads_folder = f'{script_location}/payloads/payloads_{timestamp}'

# Ensure the payloads directory exists
os.makedirs(payloads_folder, exist_ok=True)

total_payloads_to_load = []

created_files = set()

def parse_parameters():
    # Check for --help first
    if '--help' in sys.argv:
        print(help_message)
        programPause = input("Press the <ENTER> key to exit...")
        sys.exit(0)

    parser = argparse.ArgumentParser(description="Dynamically set variables from command-line arguments.")
    args, unknown_args = parser.parse_known_args()

    for arg in unknown_args:
        if arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)  # Remove "--" and split into key and value
            try:
                # Safely parse value as Python object (list, dict, etc.)
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                pass  # Leave value as-is if parsing fails

            # Handle appending to arrays or updating dictionaries
            if key in globals():
                existing_value = globals()[key]
                if isinstance(existing_value, list) and isinstance(value, list):
                    ## If what was passed is an array, we'll append to the array
                    existing_value.extend(value)  # Append to the existing array
                elif isinstance(existing_value, dict) and isinstance(value, dict):
                    ## If what was passed is a dict, we'll add to the dict
                    existing_value.update(value)  # Add or update keys in the dictionary
                else:
                    ## Otherwise, it's an ordinary variable. replace it
                    globals()[key] = value  # Replace for other types

            else:
                ## It's a new variable. Create an ordinary variable.
                globals()[key] = value  # Set as a new variable


def select_recent_csv(directory):
    """
    Lists CSV files in a given directory, sorted by most recent modification time,
    prompts the user to select one, and returns the path for the selected file.

    Args:
        directory (str): The directory to search for CSV files.

    Returns:
        str: The full path of the selected CSV file, or None if no valid file is selected.
    """
    # Expand user directory if ~ is used
    directory = os.path.expanduser(directory)

    # Check if the directory exists
    if not os.path.isdir(directory):
        print(f"Directory not found: {directory}")
        return None

    # List all CSV files in the directory
    csv_files = [
        os.path.join(directory, file)
        for file in os.listdir(directory)
        if file.endswith('.csv')
    ]

    # Check if any CSV files were found
    if not csv_files:
        print(f"No CSV files found in the directory: {directory}")
        return None

    # Sort the files by modification time (most recent first)
    csv_files.sort(key=os.path.getmtime, reverse=True)

    # Display the files to the user with their modification times
    print("Select a CSV file:")
    for i, file in enumerate(csv_files, start=1):
        ## mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(file))
        print(f"    {i}. {os.path.basename(file)}")

    # Prompt the user to select a file
    while True:
        try:
            choice = int(input(f"Enter the number of the file to select (1-{len(csv_files)}): "))
            if 1 <= choice <= len(csv_files):
                selected_file = csv_files[choice - 1]
                return selected_file
            else:
                print(f"Invalid choice. Please select a number between 1 and {len(csv_files)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def process_json_error(text):
    result_text = text
    if not show_raw_errors:
        try:
            resultJson = json.loads(text)
            result_text = resultJson['message']
        except Exception as e:
            pass
    return result_text

def deleteLookupTable(id="", name=""):
    getCredentials()
    login() 

    final_id=None
    if len(id) < 2:
        ## Check to see if the ID Already exists
        final_id = search_lookup_id_by_name(name)
    else:
        final_id = id

    try:
        this_header = headers_bearer.copy()
        this_header['X-INFA-PRODUCT-ID'] = 'MCC'


        Result = requests.delete(cdgc_url+f"/ccgf-metadata-discovery/api/v1/lookuptables/{final_id}", headers=this_header)
        resultJson = json.loads(Result.text)

        this_status = resultJson['status']
        this_message = resultJson['message']

        if this_status == 'SUCCESS':
            print(f"INFO: Lookup Table {name} deleted")
        else:
            print(f"ERROR: Lookup Table {name} Not deleted: {this_status} {this_message}")
    except Exception as e:
        print(f"ERROR: Error deleting Lookup Table {name}: {e}")    

def getLookupTables():
    getCredentials()
    login()    

#-- get custom data element classification
    os.makedirs(extracts_folder, exist_ok=True) 
    extracts_file_path = os.path.join(extracts_folder, current_lookup_file)
    extracts_file_detail_path = os.path.join(extracts_folder, current_lookup_details_file)

    try:
        if os.path.isfile(extracts_file_path):
            os.remove(extracts_file_path)
    except Exception as e:
        print(f"ERROR: Error deleting file {extracts_file_path}: {e}")

    try:
        if os.path.isfile(extracts_file_detail_path):
            os.remove(extracts_file_detail_path)
    except Exception as e:
        print(f"ERROR: Error deleting file {extracts_file_detail_path}: {e}")        

    try:
        ## Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?classificationType=DATA_ELEMENT&pageSize=2000", headers=headers_bearer)
        Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/lookuptables?pageSize=500&pageNumber=0&sortBy=name&sortOrder=asc", headers=headers_bearer)
        resultJson = json.loads(Result.text)

        with open(extracts_file_path, 'w') as extracts_file:
            json.dump(resultJson, extracts_file, indent=4)  # Pretty-print with 4-space indentation  
        created_files.add(extracts_file_path)

        if when_extracting_fetch_details:
            for i in resultJson:
                if i['origin'] != "OOTB":
                    extracts_file_detail_path = os.path.join(extracts_folder, current_lookup_details_file)
                    detail_Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/lookuptables/"+i['id'], headers=headers_bearer,timeout=120)
                    detailResultJson = json.loads(detail_Result.text)


                    if os.path.exists(extracts_file_detail_path) and os.path.getsize(extracts_file_detail_path) > 0:
                        # Read existing data
                        with open(extracts_file_detail_path, 'r') as file:
                            try:
                                data = json.load(file)  # Load existing JSON array
                            except json.JSONDecodeError:
                                data = []  # Start a new array if the file is not valid JSON
                    else:
                        data = []  # Start a new array if the file doesn't exist or is empty

                    # Append new data to the list
                    data.append(detailResultJson)

                    # Write the updated array back to the file
                    with open(extracts_file_detail_path, 'w') as file:
                        json.dump(data, file, indent=4)
            created_files.add(extracts_file_detail_path)

    except Exception as e:
        print(f"ERROR: Error Extracting Lookup Tables: {e}")                         


def getClassifications():
    getCredentials()
    login()    

#-- get custom data element classification
    os.makedirs(extracts_folder, exist_ok=True) 

    extracts_file_path = os.path.join(extracts_folder, current_classifications_file)
    extracts_file_detail_path = os.path.join(extracts_folder, current_classifications_details_file)

    try:
        if os.path.isfile(extracts_file_path):
            os.remove(extracts_file_path)
    except Exception as e:
        print(f"ERROR: Error deleting file {extracts_file_path}: {e}")

    try:
        if os.path.isfile(extracts_file_detail_path):
            os.remove(extracts_file_detail_path)
    except Exception as e:
        print(f"ERROR: Error deleting file {extracts_file_detail_path}: {e}") 

    try:
        ## Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?classificationType=DATA_ELEMENT&pageSize=2000", headers=headers_bearer)
        Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?pageSize=2000", headers=headers_bearer)
        resultJson = json.loads(Result.text)
        extracts_file_path = os.path.join(extracts_folder, current_classifications_file)
        with open(extracts_file_path, 'w') as extracts_file:
            json.dump(resultJson, extracts_file, indent=4)  # Pretty-print with 4-space indentation  
        created_files.add(extracts_file_path)

        if when_extracting_fetch_details:
            for i in resultJson:
                if i['origin'] != "OOTB":
                    extracts_file_detail_path = os.path.join(extracts_folder, current_classifications_details_file)
                    detail_Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications/"+i['id'], headers=headers_bearer,timeout=120)
                    detailResultJson = json.loads(detail_Result.text)


                    if os.path.exists(extracts_file_detail_path) and os.path.getsize(extracts_file_detail_path) > 0:
                        # Read existing data
                        with open(extracts_file_detail_path, 'r') as file:
                            try:
                                data = json.load(file)  # Load existing JSON array
                            except json.JSONDecodeError:
                                data = []  # Start a new array if the file is not valid JSON
                    else:
                        data = []  # Start a new array if the file doesn't exist or is empty

                    # Append new data to the list
                    data.append(detailResultJson)

                    # Write the updated array back to the file
                    with open(extracts_file_detail_path, 'w') as file:
                        json.dump(data, file, indent=4)
            created_files.add(current_classifications_details_file)

    except Exception as e:
        print(f"ERROR: Error Extracting Classification Tables: {e}")                         

def find_classification_id(name, file_path=os.path.join(extracts_folder, current_classifications_file)):
    def is_file_outdated(file_path):
        """Check if the file is older than one hour."""
        file_mod_time = os.path.getmtime(file_path)
        return datetime.now() - datetime.fromtimestamp(file_mod_time) > timedelta(hours=1)
    
    def load_file(file_path):
        """Load JSON data from file."""
        with open(file_path, "r") as f:
            return json.load(f)
    
    def search_id_by_name(data, name):
        """Search for the classification ID by name in the given data."""
        for item in data:
            if item.get("name") == name:
                return item.get("id")
        return None

    # Try finding the ID without refreshing the data
    if os.path.exists(file_path) and not is_file_outdated(file_path):
        data = load_file(file_path)
        result = search_id_by_name(data, name)
        if result:
            return result
    
    # If name wasn't found or file was missing/outdated, refresh the data
    getClassifications()
    
    # Load refreshed data and try finding the ID again
    if os.path.exists(file_path):
        data = load_file(file_path)
        result = search_id_by_name(data, name)
        if result:
            return result

    # Return None if the name is still not found
    return None

def search_lookup_id_by_name(lookup_name, file_path=os.path.join(extracts_folder, current_lookup_file)):

    if not current_lookup_file in created_files:
        getLookupTables()
    

    """
    Looks up the 'id' for a given 'name' in a JSON file.

    :param file_path: Path to the JSON file.
    :param lookup_name: The name to look for in the JSON data.
    :return: The 'id' associated with the given 'name', or None if not found.
    """
    try:
        # Load the JSON file
        with open(file_path, 'r') as file:
            data = json.load(file)
        
        # Iterate through the JSON objects to find the matching name
        for entry in data:
            if entry.get('name') == lookup_name:
                return entry.get('id')  # Return the id if the name matches
        
        # Return None if no match is found
        return None

    except Exception as e:
        print(f"ERROR: Error looking at lookup table by name: {e}")
        return None

def createLookupTable(name="", id="", desc="", filepath=""):
    getCredentials()
    login()

    final_id=None
    if len(id) < 2:
        ## Check to see if the ID Already exists
        final_id = search_lookup_id_by_name(name)

    filename = os.path.basename(filepath)

    result_text = None
    if final_id:
        ## If there is an ID, then update this one.
        with open(filepath, 'rb') as f:
            # Create a MultipartEncoder with the file and additional fields
            encoder = MultipartEncoder(
                fields={
                    'file': (filename, f, 'text/csv'),
                }
            )

            # Update headers to include the encoder's content type
            this_header = headers_bearer.copy()
            this_header['Content-Type'] = encoder.content_type
            this_header['X-INFA-PRODUCT-ID'] = 'MCC'

            # Perform the PUT request
            response = requests.put(
                f"{cdgc_url}/ccgf-metadata-discovery/api/v1/lookuptables/{final_id}/import",
                headers=this_header,
                data=encoder
            )

        result_text = response.text          
    else:
        ## If no ID, then create from scratch
        # Open the CSV file in binary mode
        with open(filepath, 'rb') as f:
            # Create a MultipartEncoder with the file and additional fields
            encoder = MultipartEncoder(
                fields={
                    'file': (filename, f, 'text/csv'),
                    'description': desc,
                    'name': name
                }
            )

            # Update headers to include the encoder's content type
            this_header = headers_bearer.copy()
            this_header['Content-Type'] = encoder.content_type
            this_header['X-INFA-PRODUCT-ID'] = 'MCC'

            # Perform the POST request
            response = requests.post(
                f"{cdgc_url}/ccgf-metadata-discovery/api/v1/lookuptables/import",
                headers=this_header,
                data=encoder
            )

        result_text = response.text 
    
    try:        
        result_json = json.loads(result_text) 
        status = result_json.setdefault('status', 'unknown')
        lastJobStatus = result_json.setdefault('lastJobStatus', 'unknown')
        detail = result_json.setdefault('detail', 'unknown')

        if status == 'unknown':
            if final_id:
                print(f"ERROR: Updating lookup table {name}: {result_text}")
            else:
                print(f"ERROR: Creating lookup table {name}: {result_text}")
        elif status[0].isdigit():
            if final_id:
                print(f"ERROR: Updating lookup table {name}: {status} {detail}")
            else:
                print(f"ERROR: Creating lookup table {name}: {status} {detail}")
        else:
            if final_id:
                print(f"INFO: Started update of Lookup Table: {name}: {status} {lastJobStatus}")
            else:
                print(f"INFO: Started creation of Lookup Table: {name}: {status} {lastJobStatus}")
    except:
        if final_id:
            print(f"ERROR: Updating lookup table {name}: {result_text}")
        else:
            print(f"ERROR: Creating lookup table {name}: {result_text}")

def generate_template_array(template_name, placeholder_name, values):
    # Path to the template JSON file
    template_path = os.path.join(templates_folder, f"{template_name}.json")
    
    # Check if the template exists
    if not os.path.exists(template_path):
        print(f"ERROR: Template {template_name}.json not found in {templates_folder}.")
        return []
    
    # Load the template JSON
    with open(template_path, 'r') as template_file:
        template_data = json.load(template_file)
    
    # Split the comma-separated values and trim whitespace
    values_list = [value.strip() for value in values.split(',')]
    
    # Generate an array of customized template items
    generated_array = []
    for value in values_list:
        # Convert the template to a string to replace placeholders
        template_str = json.dumps(template_data)
        placeholder = "{"+placeholder_name+"}"
        # Replace the placeholder with the current value
        formated_value = value.replace('\\', '\\\\')
        
        if placeholder_name in name_to_id_tokens:
            formated_value = find_classification_id(value)
            if not formated_value:
                formated_value = f"xxx id not found for {value}"
        customized_template_str = template_str.replace(placeholder, formated_value)


        # Convert back to a JSON object and add to the array
        customized_template_data = json.loads(customized_template_str)
        generated_array.append(customized_template_data)
    
    return generated_array


# Read the CSV file
def create_payloads():
    global total_payloads_to_load
    with open(csv_file_path, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)

        # Process each row in the CSV
        for row in reader:
            template_name = row.get('Template')
            classification_name = row.get('Classification Name', 'no_classification_name')
            lookup_name = row.get('Lookup Table Name', 'no_lookup_name')

            if classification_name != 'no_classification_name':
                # Construct the template JSON file path
                template_path = os.path.join(templates_folder, f"{template_name}.json")

                # Load the JSON template
                if not os.path.exists(template_path):
                    print(f"ERROR: Template {template_name}.json not found in {templates_folder}. Skipping.")
                    continue

                with open(template_path, 'r') as template_file:
                    template_json_str = template_file.read()
                    ## template_data = json.load(template_file)

                # Replace placeholders in the JSON template with CSV row data
                ## template_json_str = json.dumps(template_data)
                for key, value in row.items():
                    placeholder = "{"+key+"}"  # Format as placeholder (e.g., {Classification Name})
                    formated_value = value.replace('\\', '\\\\')
                    
                    if ":" in key and len(value) > 2:
                        array_template = key.split(":")[0]
                        array_placeholder = key.split(":")[1]
                        array_value = generate_template_array(array_template, array_placeholder, formated_value)
                        formated_value = json.dumps(array_value)  

                    template_json_str = template_json_str.replace(placeholder, formated_value)

                # Parse the updated JSON string back to a dictionary
                ## modified_data = json.loads(template_json_str)
                

                # Construct the payload file path with the classification name
                filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', classification_name)
                payload_file_path = os.path.join(payloads_folder, f"{filename}.json")

                # Write the modified JSON data to a new file in the payloads folder
                with open(payload_file_path, 'w') as payload_file:
                    payload_file.write(template_json_str)
                    ## json.dump(modified_data, payload_file, indent=4)
                last_payload_path_part = os.path.basename(payloads_folder)
                print(f"INFO: Created file: {last_payload_path_part}/{filename}.json")
                this_dict = {'type': 'classification', 'name': classification_name, 'file_name': payload_file_path}
                total_payloads_to_load.append(this_dict)
            
            if lookup_name != 'no_lookup_name':
                lookup_desc = row.get('Lookup Table Description', '')
                lookup_file_raw = row.get('Lookup Table File', '')
                lookup_file = script_location+"/"+lookup_file_raw
                this_dict = {'type': 'lookup', 'name': lookup_name, 'file_name': lookup_file, 'lookup_desc': lookup_desc}
                print(f"INFO: Queued creation of Lookup Table {lookup_name}")
                total_payloads_to_load.append(this_dict)                
                


def delete_classifications():
    global default_delete_csv_file

    print(f"INFO: Reading file for classifications to delete")
    with open(default_delete_csv_file, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        # Process each row in the CSV
        for row in reader:
            classification_name = row.get('Classification Name', 'no_classification_name')
            lookup_name = row.get('Lookup Table Name', 'no_lookup_name')
            action = row.get('Action', 'NOTHING')
            if action == 'DELETE' and classification_name != 'no_classification_name':
                delete_classification(classification_name)
            if action == 'DELETE' and lookup_name != 'no_lookup_name':
                deleteLookupTable(name=lookup_name)




def load_credentials_from_home():
    global default_user, default_pwd, default_pod

    def get_informatica_credentials():
        credentials_path = os.path.join(os.path.expanduser("~"), ".informatica_cdgc", "credentials")
        if not os.path.exists(credentials_path):
            print(f"Credentials file not found: {credentials_path}")
            return None

        config = configparser.ConfigParser()
        config.read(credentials_path)

        if "default" in config:
            return dict(config["default"])

        # If no default section, list available profiles and prompt user to select one
        profiles = config.sections()
        if not profiles:
            return None

        print("INFO: No 'default' profile found. Please select a profile:")
        for i, profile in enumerate(profiles, start=1):
            print(f"    {i}. {profile}")

        # Prompt user for selection
        while True:
            try:
                choice = int(input("Enter the number of the profile to use: "))
                if 1 <= choice <= len(profiles):
                    selected_profile = profiles[choice - 1]
                    print(f"Using credentials from the '{selected_profile}' profile.")
                    return dict(config[selected_profile])
                else:
                    print(f"INFO: Invalid choice. Please select a number between 1 and {len(profiles)}.")
            except ValueError:
                print("INFO: Invalid input. Please enter a valid number.")

    if len(default_user) < 1 or len(default_pwd) < 1 or len(default_pod) < 1:
        credentials_dict = get_informatica_credentials()
        if credentials_dict:
            default_user = credentials_dict.get('user')
            default_pwd = credentials_dict.get('pwd')
            default_pod = credentials_dict.get('pod')
        else:
            # Define the path to the credentials file in the user's home directory
            credentials_path = os.path.join(os.path.expanduser("~"), ".informatica_cdgc", "credentials.json")
            
            # Check if the file exists
            if os.path.exists(credentials_path):
                with open(credentials_path, 'r') as file:
                    try:
                        # Load the JSON data
                        credentials = json.load(file)
                        
                        # Set each credential individually if it exists in the file
                        if 'default_user' in credentials:
                            default_user = credentials['default_user']
                        if 'default_pwd' in credentials:
                            default_pwd = credentials['default_pwd']
                        if 'default_pod' in credentials:
                            default_pod = credentials['default_pod']
                        
                    except json.JSONDecodeError:
                        pass

def getCredentials():
    global pod
    global iics_user
    global iics_pwd
    global iics_url
    global cdgc_url
    
    load_credentials_from_home()

    if any(var not in globals() for var in ['pod', 'iics_user', 'iics_pwd', 'iics_url', 'cdgc_url']):
        if prompt_for_login_info == True:
            pod = input(f"Enter pod (default: {default_pod}): ") or default_pod
            iics_user = input(f"Enter username (default : {default_user}): ") or default_user
            iics_pwd=getpass.getpass("Enter password: ") or default_pwd   
        else:
            if len(default_pod) > 1:
                pod = default_pod
            else:
                pod = input(f"Enter pod (default: {default_pod}): ") or default_pod
            if len(default_user) > 1:
                iics_user = default_user
            else:
                iics_user = input(f"Enter username (default : {default_user}): ") or default_user
            if len(default_pwd) > 1:
                iics_pwd = default_pwd
            else:
                iics_pwd=getpass.getpass("Enter password: ") or default_pwd   
        iics_url = "https://"+pod+".informaticacloud.com"
        cdgc_url = "https://cdgc-api."+pod+".informaticacloud.com"

def login():
    global sessionID
    global orgID
    global headers
    global headers_bearer
    global jwt_token
    global api_url   
    # retrieve the sessionID & orgID & headers
    ## Test to see if I'm already logged in
    if 'jwt_token' not in globals() or len(headers_bearer) < 2:
        loginURL = iics_url+"/saas/public/core/v3/login"
        loginData = {'username': iics_user, 'password': iics_pwd}
        response = requests.post(loginURL, headers={'content-type':'application/json'}, data=json.dumps(loginData))
        try:        
            data = json.loads(response.text)   
            sessionID = data['userInfo']['sessionId']
            orgID = data['userInfo']['orgId']
            api_url = data['products'][0]['baseApiUrl']
            headers = {'Accept':'application/json', 'INFA-SESSION-ID':sessionID,'IDS-SESSION-ID':sessionID, 'icSessionId':sessionID}
        except:
            print("ERROR: logging in: ",loginURL," : ",response.text)
            quit()

        # retrieve the Bearer token
        URL = iics_url+"/identity-service/api/v1/jwt/Token?client_id=cdlg_app&nonce=g3t69BWB49BHHNn&access_code="  
        response = requests.post(URL, headers=headers, data=json.dumps(loginData))
        try:        
            data = json.loads(response.text)
            jwt_token = data['jwt_token']
            headers_bearer = {'content-type':'application/json', 'Accept':'application/json', 'INFA-SESSION-ID':sessionID,'IDS-SESSION-ID':sessionID, 'icSessionId':sessionID, 'Authorization':'Bearer '+jwt_token}        
        except:
            print("ERROR: Getting Token in: ",URL," : ",response.text)
            quit()

def load_classification_file(file_location):
    getCredentials()
    login()
    file_name = os.path.splitext(os.path.basename(file_location))[0]
    with open(file_location, 'r') as file:
        data = file.read()
        headers= {'content-type':'application/json', 'Accept':'application/json', 'Authorization':'Bearer '+jwt_token, 'X-Infa-Product-Id': 'MCC'}
        Result = requests.post(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications", headers=headers, data=data)
        if Result.status_code != 200:
            result_text = process_json_error(Result.text)
            print(f"ERROR: Loading \"{file_name}\" {result_text}")
        else:
            print(f"INFO: Loaded \"{file_name}\" successfully")

def delete_classification(classification_name):
    getCredentials()
    login()
    classification_id = find_classification_id(classification_name)

    headers= {'content-type':'application/json', 'Accept':'application/json', 'Authorization':'Bearer '+jwt_token, 'X-Infa-Product-Id': 'MCC'}
    Result = requests.delete(cdgc_url+f"/ccgf-metadata-discovery/api/v1/classifications/{classification_id}", headers=headers )
    if Result.status_code != 200:
        result_text = process_json_error(Result.text)
        print(f"ERROR: Error deleting \"{classification_name}\" {result_text}")
    else:
        print(f"INFO:  \"{classification_name}\" deletion job started successfully")


def main():
    global csv_file_path, total_payloads_to_load, default_delete_csv_file

    parse_parameters()
    if len(csv_file) > 2:

        csv_file_path = script_location+'/'+csv_file

    if len(sys.argv) > 1:
        if sys.argv[1].lower() == 'extract':
            getClassifications()
            getLookupTables()
            if pause_at_end:
                input(f"Press any Key to exit...")
            quit()
        elif sys.argv[1].lower() == 'delete':
            print(f"INFO: Preparing to BULK DELETE Classifications")
            if len(sys.argv) > 2:
                default_delete_csv_file = sys.argv[2]
            if not os.path.exists(default_delete_csv_file):
                default_delete_csv_file = select_recent_csv(script_location)                
            delete_classifications()
            if pause_at_end:
                input(f"Press any Key to exit...")
            quit()    
        elif os.path.exists(sys.argv[1]):
            csv_file_path = sys.argv[1]

    if not os.path.exists(csv_file_path):
        csv_file_path = select_recent_csv(script_location)


    create_payloads()
    if not create_payloads_only:
        if pause_before_loading:
            input(f"Press any Key to begin Loading...")
        print(f"INFO: Loading Files...")
        for this_item in total_payloads_to_load:
            if this_item['type'] == 'classification':
                filename = this_item['file_name']
                # Check if it is a file (not a subdirectory)
                if os.path.isfile(os.path.join(payloads_folder, filename)):
                    load_classification_file(os.path.join(payloads_folder, filename))
            if this_item['type'] == 'lookup':
                lookup_name = this_item['name']
                lookup_desc = this_item['lookup_desc']
                filepath = this_item['file_name']
                # Check if it is a file (not a subdirectory)
                if os.path.isfile(filepath):
                    createLookupTable(name=lookup_name, desc=lookup_desc, filepath=filepath)

    if pause_at_end:
        input(f"Press any Key to exit...")


if __name__ == "__main__":
    main()                
