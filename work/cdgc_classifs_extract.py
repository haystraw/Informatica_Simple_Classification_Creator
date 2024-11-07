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
    global api_url   
    # retrieve the sessionID & orgID & headers
    loginURL = iics_url+"/saas/public/core/v3/login"
    loginData = {'username': iics_user, 'password': iics_pwd}
    response = requests.post(loginURL, headers={'content-type':'application/json'}, data=json.dumps(loginData),timeout=120)
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
    response = requests.post(URL, headers=headers, data=json.dumps(loginData),timeout=120)
    try:        
        data = json.loads(response.text)
        jwt_token = data['jwt_token']
        headers_bearer = {'content-type':'application/json', 'Accept':'application/json', 'INFA-SESSION-ID':sessionID,'IDS-SESSION-ID':sessionID, 'icSessionId':sessionID, 'Authorization':'Bearer '+jwt_token}        
    except:
        print("ERROR Getting Token in: ",URL," : ",response.text)
        quit()

def getCustomDataElementClassifications():
#-- get custom data element classification 
    with open('./cdgc/classifs/CustomDataElementClassifications.csv', 'w', encoding='utf8', newline='') as csv_file:
        writer_source = csv.writer(csv_file)
        writer_source.writerow(['Name','File'])
        line_count = 0  
        Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?classificationType=DATA_ELEMENT&pageSize=2000", headers=headers_bearer)
        resultJson = json.loads(Result.text)
        for i in resultJson:
            if i['origin'] != "OOTB":
                print("INFO: Extracting Custom Data Element Classification :"+i['name']+" using Admin User: "+iics_user)
                file_name= re.sub(r'[\/:*?"<>|]', '_', i['name']).strip()               # replace special characters with underscore                         
                file_name = re.sub(r'\s+', '_', file_name)+str(line_count)+'.json'      # replace multiple spaces with a single underscore
                writer_source.writerow([i['name'],file_name])
                with open('./cdgc/classifs/'+file_name, 'w', encoding='utf8') as outfile: 
                    Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications/"+i['id'], headers=headers_bearer,timeout=120)
                    outfile.write(Result.text)
                line_count += 1
        print(f'INFO: Processed {line_count} lines.')    

def getDataEntiyClassifications():
#-- get classification dictionary    
    Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?classificationType=DATA_ELEMENT&pageSize=2000", headers=headers_bearer)
    resultJson = json.loads(Result.text)
    classifDict = {}
    for i in resultJson:
        classifDict[i['id']] = i['name']
#-- get data entity classification  
    with open('./cdgc/entities/DataEntityClassifications.csv', 'w', encoding='utf8', newline='') as entity_file:
        writer_source = csv.writer(entity_file)
        writer_source.writerow(['Name','File'])
        line_count = 0  
        Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications?classificationType=DATA_ENTITY&pageSize=2000", headers=headers_bearer,timeout=120)
        resultJson = json.loads(Result.text)
        for i in resultJson:
            print("INFO: Extracting Data Entity Classification :"+i['name']+" using Admin User: "+iics_user)
            file_name= re.sub(r'[\/:*?"<>|]', '_', i['name']).strip()               # replace special characters with underscore  
            file_name = re.sub(r'\s+', '_', file_name)+str(line_count)+'.json'      # replace multiple spaces with underscore + add number if duplicates
            writer_source.writerow([i['name'],file_name])
            with open('./cdgc/entities/'+file_name, 'w', encoding='utf8') as outfile: 
                Result = requests.get(cdgc_url+"/ccgf-metadata-discovery/api/v1/classifications/"+i['id'], headers=headers_bearer,timeout=120)
                text=Result.text
                for key in classifDict.keys() : 
                    text=re.sub(key, classifDict[key], text)
                outfile.write(text)
            line_count += 1
        print(f'INFO: Processed {line_count} lines.')    
       
def main():
    if not os.path.exists('./cdgc'): os.mkdir('./cdgc')
    if not os.path.exists('./cdgc/classifs'): os.mkdir('./cdgc/classifs')
    if not os.path.exists('./cdgc/entities'): os.mkdir('./cdgc/entities')
    start_time = time.time()
    getCredentials()
    login()
    getCustomDataElementClassifications()
    getDataEntiyClassifications()
    end_time = time.time()
    print("Execution time:", round((end_time - start_time) / 60), "minutes")
if __name__ == "__main__":
    main()
    