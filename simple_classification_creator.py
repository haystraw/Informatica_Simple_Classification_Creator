import os
import csv
import json
import requests
import getpass
import sys
from datetime import datetime, timedelta

version = 20241108

'''
pip install requests
'''


default_pod="dmp-us"        
default_user="shayes_compass"
default_pwd=""


prompt_for_login_info = True
pause_before_loading = False
create_payloads_only = False
when_extracting_fetch_details = True
show_raw_errors = False


# Paths
csv_file_path = './classifications.csv'
templates_folder = './templates'
extracts_folder = './extracts'
current_classifications_file = "current_classifications.json"
current_classifications_details_file = "current_classifications_details.json"
name_to_id_tokens = ["Classification Members"]

default_delete_csv_file = "./classifications_delete.csv"

# Get the current timestamp for folder creation
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
payloads_folder = f'./payloads/payloads_{timestamp}'

# Ensure the payloads directory exists
os.makedirs(payloads_folder, exist_ok=True)

def process_json_error(text):
    result_text = text
    if not show_raw_errors:
        try:
            resultJson = json.loads(text)
            result_text = resultJson['message']
        except Exception as e:
            pass
    return result_text

def getClassifications():
    getCredentials()
    login()    

#-- get custom data element classification
    os.makedirs(extracts_folder, exist_ok=True) 
    for filename in os.listdir(extracts_folder):
        file_path = os.path.join(extracts_folder, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)  # Delete the file
        except Exception as e:
            print(f"ERROR: Error deleting file {file_path}: {e}")

    ## Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?classificationType=DATA_ELEMENT&pageSize=2000", headers=headers_bearer)
    Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?pageSize=2000", headers=headers_bearer)
    resultJson = json.loads(Result.text)
    extracts_file_path = os.path.join(extracts_folder, current_classifications_file)
    with open(extracts_file_path, 'w') as extracts_file:
        json.dump(resultJson, extracts_file, indent=4)  # Pretty-print with 4-space indentation  

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
    with open(csv_file_path, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)

        # Process each row in the CSV
        for row in reader:
            template_name = row.get('Template')
            classification_name = row.get('Classification Name', 'default_name')

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
            payload_file_path = os.path.join(payloads_folder, f"{classification_name}.json")

            # Write the modified JSON data to a new file in the payloads folder
            with open(payload_file_path, 'w') as payload_file:
                payload_file.write(template_json_str)
                ## json.dump(modified_data, payload_file, indent=4)

            print(f"INFO: Created file: {payload_file_path}")

def delete_classifications():
    print(f"INFO: Reading file for classifications to delete")
    with open(default_delete_csv_file, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        # Process each row in the CSV
        for row in reader:
            classification_name = row.get('Classification Name')
            action = row.get('Action', 'NOTHING')
            if action == 'DELETE':
                delete_classification(classification_name)

def getCredentials():
    global pod
    global iics_user
    global iics_pwd
    global iics_url
    global cdgc_url

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

if len(sys.argv) > 1:
    if sys.argv[1].lower() == 'extract':
        getClassifications()
        quit()
    elif sys.argv[1].lower() == 'delete':
        if len(sys.argv) > 2:
            default_delete_csv_file = sys.argv[2]
        delete_classifications()
        quit()    
    else:
        csv_file_path = sys.argv[1]


create_payloads()
if not create_payloads_only:
    if pause_before_loading:
        input(f"Press any Key to begin Loading...")
    print(f"INFO: Loading Files...")
    for filename in os.listdir(payloads_folder):
        # Check if it is a file (not a subdirectory)
        if os.path.isfile(os.path.join(payloads_folder, filename)):
            load_classification_file(os.path.join(payloads_folder, filename))
