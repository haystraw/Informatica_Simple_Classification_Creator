import os, csv, requests, json, getpass, time, re
#-- default pod, user (must be admin), and password
default_pod="dmp-us"        
default_user="shayes_compass"
default_pwd="Infa2024!"

def getCredentials():
    global pod
    global iics_user
    global iics_pwd
    global iics_url
    global cdgc_url
    pod = input(f"Enter pod (default: {default_pod}): ") or default_pod
    iics_user = input(f"Enter username (default : {default_user}): ") or default_user
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
        print("ERROR logging in: ",loginURL," : ",response.text)
        quit()

    # retrieve the Bearer token
    URL = iics_url+"/identity-service/api/v1/jwt/Token?client_id=cdlg_app&nonce=g3t69BWB49BHHNn&access_code="  
    response = requests.post(URL, headers=headers, data=json.dumps(loginData))
    try:        
        data = json.loads(response.text)
        jwt_token = data['jwt_token']
        headers_bearer = {'content-type':'application/json', 'Accept':'application/json', 'INFA-SESSION-ID':sessionID,'IDS-SESSION-ID':sessionID, 'icSessionId':sessionID, 'Authorization':'Bearer '+jwt_token}        
    except:
        print("ERROR Getting Token in: ",URL," : ",response.text)
        quit()

def createCustomDataElementClassifications():
#-- create custom data element classification 
    with open('./cdgc/classifs/CustomDataElementClassifications.csv') as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter=',')
        line_count = 0
        for row in csv_reader: 
            print("INFO: Creating Custom Data Element Classification :"+row['Name']+" using Admin User: "+iics_user)
            with open('./cdgc/classifs/'+row['File'], 'r') as file:
                data = file.read()
                headers= {'content-type':'application/json', 'Accept':'application/json', 'Authorization':'Bearer '+jwt_token, 'X-Infa-Product-Id': 'MCC'}
                Result = requests.post(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications", headers=headers, data=data)
                if Result.status_code != 200:
                    print(Result.text)
            line_count += 1
        print(f'INFO: Processed {line_count} lines.')    

def createDataEntiyClassifications():
#-- get classification dictionary sorted by name length
    Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?classificationType=DATA_ELEMENT&pageSize=2000", headers=headers_bearer)
    resultJson = json.loads(Result.text)
    classifDict = {}
    for i in resultJson:
        classifDict[i['name']] = i['id']
    sorted_classifDict = dict(sorted(classifDict.items(), key=lambda item: len(item[0]), reverse=True))
#-- create data entity classification 
    with open('./cdgc/entities/DataEntityClassifications.csv') as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter=',')
        line_count = 0
        for row in csv_reader: 
            print("INFO: Creating Custom Data Entity Classification :"+row['Name']+" using Admin User: "+iics_user)
            with open('./cdgc/entities/'+row['File'], 'r') as file:
                data = file.read()
                #-- classification name->id replacement                 
                for key in sorted_classifDict.keys() : 
                    data=re.sub(key, sorted_classifDict[key], data)
                headers= {'content-type':'application/json', 'Accept':'application/json', 'Authorization':'Bearer '+jwt_token, 'X-Infa-Product-Id': 'MCC'}
                Result = requests.post(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications", headers=headers, data=data)
                if Result.status_code != 200:
                    print(Result.text)
            line_count += 1
        print(f'INFO: Processed {line_count} lines.')  
       
def main():
    if not os.path.exists('./cdgc'): 
        print("ERROR: no content found")
        quit()
    start_time = time.time()
    getCredentials()
    login()
    createCustomDataElementClassifications()
    createDataEntiyClassifications()
    end_time = time.time()
    print("Execution time:", round((end_time - start_time) / 60), "minutes")
if __name__ == "__main__":
    main()
    