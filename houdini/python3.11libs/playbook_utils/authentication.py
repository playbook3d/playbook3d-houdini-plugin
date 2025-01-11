import os
import json
import base64
import requests
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from playbook_utils.secret_manager import HoudiniSecretsManager

def decode_jwt(token: str) -> str:
    """Decode a JWT token to extract user information."""
    base64_url = token.split(".")[1]
    base64_str = base64_url.replace("-", "+").replace("_", "/")
    padded_base64_str = base64_str + "=" * (4 - len(base64_str) % 4)
    
    decoded_bytes = base64.b64decode(padded_base64_str)
    return decoded_bytes.decode("utf-8")

def get_user_info(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate user with API key and get user information.
    Args:
        api_key (str): The user's API key from Playbook3D web editor
    Returns:
        Optional[Dict[str, Any]]: Dictionary containing user email and credits if successful,
                                None if authentication fails
    """
    try:
        # Get URLs and API key from AWS Secrets Manager
        secrets = HoudiniSecretsManager.get_secret()
        
        alias_url = secrets.get('ALIAS_URL')
        user_url = secrets.get('USER_URL')
        x_api_key = secrets.get('X_API_KEY')
        
        if not all([alias_url, user_url, x_api_key]):
            print("Missing required configuration from AWS Secrets")
            return None

        # Get access token using API key
        token_url = f"{alias_url}{api_key}"
        print(f"Requesting token from: {token_url}")
        
        jwt_request = requests.get(token_url)
        
        if jwt_request.status_code != 200:
            print(f"Failed to get access token. Status code: {jwt_request.status_code}")
            print(f"Response: {jwt_request.text}")
            return None

        access_token = jwt_request.json()["access_token"]
        
        # Decode JWT to get username
        decoded_jwt = decode_jwt(access_token)
        decoded_json = json.loads(decoded_jwt)
        username = decoded_json["username"]

        # Get user information using username and access token
        info_url = user_url.replace("*", username)
        print(f"Requesting user info from: {info_url}")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "x-api-key": x_api_key
        }
        
        user_request = requests.get(url=info_url, headers=headers)
        if user_request.status_code != 200:
            print(f"Failed to get user info. Status code: {user_request.status_code}")
            print(f"Response: {user_request.text}")
            return None

        user_data = user_request.json()
        print(f"User info: {user_data}")
        return {
            "email": user_data["email"],
            "credits": user_data["users_tier"]["credits"]
        }

    except Exception as e:
        print(f"Authentication error: {str(e)}")
        return None


def get_user_token() -> str:
    """
    Get the user token from Playbook3D web editor.
    Returns:
        str: The user token.
    """
    api_key = os.getenv("PLAYBOOK_API_KEY")

    if not api_key:
        raise ValueError("Playbook API key not found in environment variables")
    
    jwt_request = requests.get(f"{base_url}/token-wrapper/get-tokens/{api_key}")

    try:
        if jwt_request.status_code != 200:
            raise ValueError(f"Failed to get token. Status code: {jwt_request.status_code}")
    except Exception as e:
        print(f"Error getting token: {e}")
        raise ValueError("Failed to authenticate with API key")

    return __parse_jwt_data__(jwt_request.json()["access_token"])  


def load_dotenv() -> None:
    """
    Load the .env file.
    """
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path=env_path)
    

def validate_api_key(api_key: str) -> bool:
    """
    Validate if the provided API key has the correct format and can authenticate.
    Args:
        api_key (str): The API key to validate
    Returns:
        bool: True if the API key is valid, False otherwise
    """
    if not api_key or len(api_key) != 36:
        return False
    
    user_info = get_user_info(api_key)
    return user_info is not None
