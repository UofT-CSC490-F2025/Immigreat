import json
import boto3

s3_client = boto3.client('s3')

def handler(event, context):
    """
    Process JSON files uploaded to S3 and print filename
    """
    print("Lambda function triggered!")
    
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        file_key = record['s3']['object']['key']
        
        print(f"New JSON file detected: {file_key}")
        print(f"Bucket: {bucket_name}")
        print(f"Full path: s3://{bucket_name}/{file_key}")
        
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            file_content = response['Body'].read().decode('utf-8')
            
            json_data = json.loads(file_content)
            
            print(f"JSON file size: {len(file_content)} bytes")
            print(f"JSON keys: {list(json_data.keys()) if isinstance(json_data, dict) else 'Not a JSON object'}")
            
        except Exception as e:
            print(f"Error processing file {file_key}: {str(e)}")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Successfully processed JSON file')
    }