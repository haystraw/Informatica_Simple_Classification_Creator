import os
import csv
import json
import requests
import getpass
from datetime import datetime

default_pod="dmp-us"        
default_user="shayes_compass"
default_pwd="Infa2024!"


prompt_for_login_info = True


# Paths
csv_file_path = './classifications.csv'
templates_folder = './templates'

# Get the current timestamp for folder creation
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
payloads_folder = f'./payloads/payloads_{timestamp}'

# Ensure the payloads directory exists
os.makedirs(payloads_folder, exist_ok=True)

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
                template_data = json.load(template_file)

            # Replace placeholders in the JSON template with CSV row data
            template_json_str = json.dumps(template_data)
            for key, value in row.items():
                placeholder = "{"+key+"}"  # Format as placeholder (e.g., {Classification Name})
                template_json_str = template_json_str.replace(placeholder, value).replace('\\', '\\\\')

            # Parse the updated JSON string back to a dictionary
            modified_data = json.loads(template_json_str)

            # Construct the payload file path with the classification name
            payload_file_path = os.path.join(payloads_folder, f"{classification_name}.json")

            # Write the modified JSON data to a new file in the payloads folder
            with open(payload_file_path, 'w') as payload_file:
                json.dump(modified_data, payload_file, indent=4)

            print(f"INFO: Created file: {payload_file_path}")


def getCredentials():
    global pod
    global iics_user
    global iics_pwd
    global iics_url
    global cdgc_url


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
        if len(iics_pwd) > 1:
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
    file_name = os.path.splitext(os.path.basename(file_location))[0]
    with open(file_location, 'r') as file:
        data = file.read()
        headers= {'content-type':'application/json', 'Accept':'application/json', 'Authorization':'Bearer '+jwt_token, 'X-Infa-Product-Id': 'MCC'}
        Result = requests.post(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications", headers=headers, data=data)
        if Result.status_code != 200:
            print(f"ERROR: Loading \"{file_name}\" {Result.text}")
        else:
            print(f"INFO: Loaded \"{file_name}\" successfully")


getCredentials()
create_payloads()
login()
print(f"INFO: Loading Files...")
for filename in os.listdir(payloads_folder):
    # Check if it is a file (not a subdirectory)
    if os.path.isfile(os.path.join(payloads_folder, filename)):
        load_classification_file(os.path.join(payloads_folder, filename))
