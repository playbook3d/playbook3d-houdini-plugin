import boto3
from botocore.exceptions import ClientError
import json
import os
from typing import Dict, Any
from dotenv import load_dotenv

# load .env file
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

class HoudiniSecretsManager:
    """
    AWS Secrets Manager client for Houdini plugin
    """
    DEFAULT_REGION = "us-east-2"
    
    @staticmethod
    def _get_client(region_name: str = DEFAULT_REGION) -> boto3.client:
        try:
            session = boto3.session.Session(
                aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
                region_name=region_name
            )
            return session.client('secretsmanager')
            
        except Exception as e:
            raise Exception(f"Failed to initialize AWS client: {str(e)}")

    @staticmethod
    def get_secret(secret_name: str = None, region_name: str = DEFAULT_REGION) -> Dict[str, Any]:
        if secret_name is None:
            secret_name = os.environ.get('SECRET_NAME')
            if not secret_name:
                raise ValueError("SECRET_NAME not found in environment variables")
                
        client = HoudiniSecretsManager._get_client(region_name)
        try:
            response = client.get_secret_value(SecretId=secret_name)
            
            if 'SecretString' in response:
                return json.loads(response['SecretString'])
            else:
                raise ValueError(f"Secret {secret_name} has no SecretString")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            raise Exception(f"AWS Error ({error_code}): {error_message}")
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse secret value as JSON: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error accessing secret: {str(e)}")
