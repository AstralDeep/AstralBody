import requests
import json
import pandas as pd
from time import sleep

url = "https://classify.ai.uky.edu"
headers = {'Authorization': f'Bearer {API_KEY}', 'Accept': 'application/json'}

def startJob(dataset_path, class_column): # Pass in path to csv dataset and name of desired class column

    # STEP 1: Upload the csv file and retrieve the response.
    with open(dataset_path, 'rb') as file:
        files = {'file': file}
        response = requests.post(url + '/reports/submit', files=files, headers=headers}
    upload_response = json.loads(response.text)
    report_uuid = upload_response['report_uuid']
    column_types = upload_response['column_types']['data_types']

    # STEP 2: Format the column types.
    df = pd.read_csv(dataset_path)
    column_result = []
    for key in column_types.keys():
        has_missing = df[key].isnull().any()
        if has_missing:
            missing = 'synthetic' # Using synthetic fill by default, can change this to 'constant' and set the 'fill_value' attribute instead
        else:
            missing = None
        column_type = {'column': key, 'data_type': column_types[key], 'checked': True, 'missing': missing, 'fill_value': None} # Can set checked = False to exclude certain columns
        if key == class_column:
            column_type['class'] = True
        column_result.append(column_type)
    response = requests.post(url + '/reports/set-column-changes', data={'report_uuid': report_uuid, 'column_changes': json.dumps(column_result)}, headers=headers)

    # STEP 3: Get and format parameters for training job, and begin the job.
    response = requests.get(url + '/reports/get-ml-opts', params={'unsstate': 0}, headers=headers) # Set unsstate = 1 for unsupervised learning
    parameters = json.loads(response.text)['parameters']
    args = []
    models_to_train = ['random_forest', 'gradientboosting'] # Modify this to change which models should be trained
    for key in parameters.keys():
        if key == 'train_group': # The parameter that determines the trained models
            for model in parameters[key]['default']:
                if model in models_to_train:
                    args.append({'name': key, 'value': model})
        else:
            value = parameters[key]['default'] # Get the default value for that parameter
            if key == 'parameter_tune': # This turns the parameter tuning option off, can modify and add more conditions to alter job parameters further.
                value = False
            args.append({'name': key, 'value': value})
    args.append({'name': 'report_uuid', 'value': report_uuid})
    args.append({'name': 'class_column', 'value': class_column})
    args.append({'name': 'supervised', 'value': 'True'}) # For supervised learning
    args.append({'name': 'autodetermineclusters', 'value': 'False'}) # Only matters if supervised is False
    response = requests.post(url + '/reports/start-training-job', data={'report_uuid': report_uuid, 'options': json.dumps(args)}, headers=headers}

    # Step 4: Check status of job to monitor progress.
    while True: # Can begin a loop to wait until the job is finished (for example purposes, not recommended in practice for long jobs)
        response = requests.get(url + '/reports/get-job-status', params={'report_uuid': report_uuid}, headers=headers)
        status = json.loads(response.text)['status']
        if status == 'Processed': # The job is complete!
            break
        elif status == 'Processing' or 'Processed' in status: # For instance, '1/10 Processed' indicates the job is still running
            print('Job is still running!')
        else: #There was some problem
            print(f'Status: {status}')
            break
        sleep(30) # Check the status every 30 seconds

    # Step 5: Get the results of the job
    response = requests.get(url + '/result/get-results', params={'report_uuid':report_uuid}, headers=headers)
    results = response.text
    print(results)