import hou
import collections
import requests
import jwt
import json
import os

from playbook_utils.authentication import get_user_token

BASE_URL = "https://dev-accounts.playbook3d.com"

def add_mask(node: hou.Node):
    """Add a mask by updating the masks multiparm list on the node.
    
    This function handles the creation and management of mask parameters in the Houdini node.
    It updates the multiparm list that controls mask settings.

    Args:
        node (hou.Node): The Houdini node to add the mask to
    """
    cur_num_masks = node.parm("masks").eval()

    # Allow maximum of 7 masks
    if cur_num_masks >= 7:
        hou.ui.displayMessage("Maximum number of masks reached.")
        return

    new_num_masks = cur_num_masks + 1
    node.parm("masks").set(new_num_masks)


def authenticate_user(node: hou.Node):
    """Authenticate user with Playbook API and update node parameters.
    
    This function validates the API key, retrieves user information from Playbook,
    and updates the node parameters with user email and available credits.

    Args:
        node (hou.Node): The Houdini node to update with user information

    Raises:
        ValueError: If the API key is invalid or not found
    """
    api_key = hou.getenv("PLAYBOOK_API_KEY")
    if validate_api_key(api_key):
        # Get user information
        user_info = get_user_info(api_key)
        if user_info:
            email = user_info["email"]
            node.parm("user_email").set(email)
            credits = user_info["credits"]
            node.parm("user_credits").set(credits)
    else:
        hou.ui.displayMessage("Invalid API key. Please make sure the API key present in the package is valid.")


def clear_masks(node: hou.Node):
    """Clear all masks from the node.
    
    This function removes all mask entries by setting the masks multiparm list to 0,
    effectively clearing all mask-related parameters and their associated data.

    Args:
        node (hou.Node): The Houdini node to clear masks from
    """
    node.parm("masks").set(0)


def remove_mask(node: hou.Node, index: str):
    """Remove a specific mask from the node.
    
    This function removes the mask at the specified index and updates all related
    object merge nodes to maintain consistency in the node network.

    Args:
        node (hou.Node): The Houdini node to remove mask from
        index (str): The index of the mask to remove (1-based indexing)
    """
    node.parm("masks").removeMultiParmInstance(int(index) - 1)

    # Update the object merge nodes
    update_object_merge_nodes(node)


def update_object_merge_nodes(node: hou.Node, index: str = None):
    """Update object merge nodes to reflect current mask configuration.
    
    This function synchronizes the object merge nodes with the current mask settings.
    It can update either all masks or a specific mask if an index is provided.

    Args:
        node (hou.Node): The Houdini node containing the object merge nodes
        index (str, optional): Specific mask index to update. If None, updates all masks
    """
    indices = get_indices(node, index)
    check_for_repeated_object_nodes(node, indices)
    if index:
        indices = [index]

    for idx in indices:
        update_selected_objmerge_node(node, idx)


def get_indices(node: hou.Node, index: str = None):
    """Get list of valid mask indices for processing.
    
    This function returns a list of indices to process, either all possible indices
    or a specific one if provided. The indices are 1-based to match Houdini's convention.

    Args:
        node (hou.Node): The Houdini node to get indices for
        index (str, optional): Specific index to return. If None, returns all possible indices

    Returns:
        list[str]: List of indices as strings, using 1-based indexing
    """
    max_num_masks = 8
    all_indices = [str(i + 1) for i in range(max_num_masks)]

    return all_indices


def check_for_repeated_object_nodes(node: hou.Node, indices: list):
    """Check for duplicate object node references in masks.
    
    This function identifies any object nodes that are used in multiple masks
    and displays a warning message if duplicates are found. This helps prevent
    unintended mask overlaps.

    Args:
        node (hou.Node): The Houdini node to check for duplicates
        indices (list): List of mask indices to check

    Raises:
        hou.ui.displayMessage: If duplicate object nodes are found
    """
    all_object_nodes = []
    for cur_idx in indices:
        if node.parm(f"objects{cur_idx}"):
            object_nodes = hou.node("/obj").glob(node.evalParm(f"objects{cur_idx}"))
            all_object_nodes.extend(object_nodes)

    if len(all_object_nodes) != len(set(all_object_nodes)):
        repeated_object_nodes = [item for item, count in collections.Counter(all_object_nodes).items() if count > 1]
        hou.ui.displayMessage(
            f"Warning: The following object nodes are repeated: \n{repeated_object_nodes}\n"
            "Please ensure that each object node is only used once in the masks."
        )


def update_selected_objmerge_node(node: hou.Node, idx: str):
    """Update a specific object merge node's configuration.
    
    This function updates the object merge node for a specific mask index,
    connecting it to the appropriate object nodes and handling special cases
    like cameras and self-references.

    Args:
        node (hou.Node): The Houdini node containing the object merge node
        idx (str): The index of the mask to update

    Note:
        - Automatically filters out camera nodes
        - Prevents self-referencing by excluding the current node
    """
    object_merge_nodes = node.glob(f"masks/mask{idx}/object_merge1")
    for object_merge_node in object_merge_nodes:
        if node.parm(f"objects{idx}"):
            object_pattern = node.evalParm(f"objects{idx}")
            object_nodes = hou.node("/obj").glob(object_pattern)
            # Remove the current HDA node from the object nodes
            # Also remove objects nodes of type cam
            object_nodes = [object_node for object_node in object_nodes if object_node.type().name() != "cam"]
            object_nodes = [object_node for object_node in object_nodes if object_node != node]

            # Set the object nodes in object merge node
            object_merge_node.parm("numobj").set(0)
            object_merge_node.parm("numobj").set(len(object_nodes))
            for j, object_node in enumerate(object_nodes):
                object_merge_node.parm(f"objpath{j + 1}").set(object_node.path())
        else:
            object_merge_node.parm("numobj").set(0)


def submit_to_playbook(node: hou.Node):
    """Submit the current node's render to Playbook for processing.
    
    This function handles the complete workflow of rendering, uploading, and downloading
    results from Playbook. It performs the following steps:
    1. Renders the current node state
    2. Uploads the render passes to S3 storage
    3. Downloads the processed render from Playbook
    
    Args:
        node (hou.Node): The Houdini node to process
    """
    # Render the passes
    hou.ui.setStatusMessage("Rendering passes...")
    image_data = render(node)

    # Upload the render passes in s3 storage
    hou.ui.setStatusMessage("Submitting to Playbook...")
    download_urls = upload_render_passes(node, image_data)

    # Download the render from playbook
    hou.ui.setStatusMessage("Downloading render...")
    download_render(node, download_urls)


def update_teams(node: hou.Node):
    """Update the teams dropdown menu with data from Playbook API.
    
    This function fetches the available teams from the Playbook API and updates
    the node's team selection dropdown menu. The teams data is cached in the node
    for future use.

    TODO: 
    - Currently not working and needs implementation
    - Teams data needs to be fetched from Playbook API
    
    Args:
        node (hou.Node): The Houdini node to update teams for
    """
    teams_list = ["select", "select"]
    # TODO: Get teams data from playbook API. This code is currently not working. 
    teams_url = f"{BASE_URL}/teams"

    user_token = get_user_token()  

    # Note : The X_API_KEY needs to be stored in .env file. It can be retrieved using os.getenv("PLAYBOOK_X_API_KEY")
    x_api_key = os.getenv("PLAYBOOK_X_API_KEY")

    account_headers = {"Authorization": f"Bearer {user_token}", "x-api-key": x_api_key}

    teams = requests.get(teams_url, headers=account_headers)
    # print(f"teams: {teams.json()}") # Debug
    # Note, teams should be a list of strings

    # Team list needs to have a name and value for the houdini dropdown menu. This can be same values. 

    for team in teams.json():
        teams_list.append(team["name"])
        teams_list.append(team["name"])

    # Cache the teams list data in the node
    # The cached data needs to be of type string
    node.cacheUserData("teams", json.dumps(teams_list))

    # Since the teams data is updated, the workflows needs to be updated as well
    update_workflows(node)


def update_workflows(node: hou.Node):
    """Update the workflows dropdown menu with data from Playbook API.
    
    This function fetches available workflows from the Playbook API and updates
    the node's workflow selection dropdown menu. The workflows data is cached 
    in the node for future use.

    TODO:
    - Currently not working and needs implementation
    - Workflows data needs to be fetched from Playbook API
    
    Args:
        node (hou.Node): The Houdini node to update workflows for
    """
    # TODO: Get workflows data from playbook API. This code is currently not working. 
    workflows_url = f"{BASE_URL}/workflows"

    # Note: API Key needs to be satored in .env file. It can be retrieved using os.getenv("PLAYBOOK_API_KEY")
    api_key = os.getenv("PLAYBOOK_API_KEY")

    user_token = get_user_token()  
    account_headers = {"Authorization": f"Bearer {user_token}", "x-api-key": api_key}

    workflows = requests.get(workflows_url, headers=account_headers)
    # print(f"workflows: {workflows.json()}") # Debug
    # Note, workflows should be a list of strings

    # Workflows list needs to have a name and value for the houdini dropdown menu. This can be same values. 

    workflows_list = ["select", "select"]
    for workflow in workflows.json():
        workflows_list.append(workflow["name"])
        workflows_list.append(workflow["name"])

    # Cache the workflows list data in the node
    # The cached data needs to be of type string
    node.cacheUserData("workflows", json.dumps(workflows_list))


def render(node):
    """Render the current node state and collect image data.
    
    This function handles the rendering process of the node and collects
    all the rendered image data for further processing.

    Args:
        node: The Houdini node to render

    Returns:
        list: A list containing all rendered image data
    """
    all_img_data = []
    render_passes = ["beauty", "depth", "masks", "canny", "normals"]
    cop_path = hou.node(node.path() + "/renderer/cop2net1")

    # Collect all render passes
    for render_pass in render_passes:
        cop_out_node = hou.node(cop_path.path() + f"/{render_pass}")
        cop_out_node.parm("execute").pressButton()
        all_img_data.append(cop_out_node.parm("copoutput").eval())

    # print(f"Image data: {all_img_data}")
    return all_img_data


def upload_render_passes(node: hou.Node, image_data: list):
    """Upload render passes to Playbook's S3 storage.
    
    This function handles the upload process of rendered images to Playbook's S3 storage.
    It requires a selected team and workflow before uploading. For each image:
    1. Gets an upload URL from Playbook
    2. Uploads the image data
    3. Gets a download URL for later use

    TODO:
    - Implement the complete Playbook API integration for storing render passes in S3
    
    Args:
        node (hou.Node): The Houdini node containing render settings
        image_data (list): List of rendered images to upload

    Returns:
        list: List of download URLs for all uploaded images

    Raises:
        ValueError: If team or workflow is not selected, or if upload process fails
    """
    # TODO: Call playbook API to store the render passes in s3
    download_urls = []
    selected_team = node.evalParm("team")
    selected_workflow = node.evalParm("workflow")

    if selected_team == "select" or selected_workflow == "select":
        raise ValueError("Please select a team and workflow before submitting to Playbook")

    user_token = get_user_token()
    x_api_key = os.getenv("PLAYBOOK_X_API_KEY")

    headers = {"Authorization": f"Bearer {user_token}", "x-api-key": x_api_key}
    for img_data in image_data:
        try:
            # Get upload URL
            result_request = requests.get(f"{BASE_URL}/upload-assets/get-upload-urls", headers=headers)
            if result_request.status_code != 200:
                raise ValueError(f"Failed to get upload URL. Status code: {result_request.status_code}")
            
            result_url = result_request.json()["save_result"]
            print(f"Got upload URL: {result_url}")
            
            # Upload image
            result_response = requests.put(url=result_url, data=img_data)
            if result_response.status_code != 200:
                raise ValueError(f"Failed to upload image. Status code: {result_response.status_code}")
            
            # Get download URL
            download_request = requests.get(f"{BASE_URL}/upload-assets/get-download-urls", headers=headers)
            if download_request.status_code != 200:
                raise ValueError(f"Failed to get download URL. Status code: {download_request.status_code}")
            
            download_url = download_request.json()["save_result"]
            print(f"Upload successful. Download URL: {download_url}")
            download_urls.append(download_url)
            
        except Exception as e:
            print(f"Error uploading image: {e}")
            continue  # Continue with next image even if one fails
    
    if not download_urls:
        raise ValueError("Failed to upload any images successfully")
    
    return download_urls


def download_render(node: hou.Node, download_urls: list):
    """Download processed renders from Playbook.
    
    This function handles downloading the processed render results from Playbook
    using the provided download URLs.

    TODO:
    - Implement Playbook API integration for downloading processed renders
    
    Args:
        node (hou.Node): The Houdini node to store downloaded renders
        download_urls (list): List of URLs to download the processed renders from
    """
    # TODO: Call playbook API to download the render
    pass


def __parse_jwt_data__(token: str) -> dict | None:
    """Parse and decode JWT token data.
    
    This internal function handles the parsing and decoding of JWT tokens
    used in Playbook authentication.

    Args:
        token (str): The JWT token to parse

    Returns:
        dict | None: Decoded token data as dictionary if successful, None otherwise
    """
    try:
        payload_segment = token.split(".")[1]
        payload_bytes = payload_segment.encode("ascii")
        payload_json = jwt.utils.base64url_decode(payload_bytes)
        payload = json.loads(payload_json)
        return payload
    except(IndexError, UnicodeDecodeError, ValueError) as e:
        print(e)
        raise ValueError
