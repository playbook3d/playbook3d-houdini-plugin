import hou
import collections

from playbook_utils import network
from playbook_utils.network import ComfyDeployClient, GlobalRenderSettings, RetextureRenderSettings, StyleTransferRenderSettings, MaskData

def add_mask(node: hou.Node):
    """Add a mask by updating the masks multiparm list on the node.

    Args:
        node (hou.node): current HDA
    """
    cur_num_masks = node.parm("masks").eval()

    # Allow maximum of 7 masks
    if cur_num_masks >= 7:
        hou.ui.displayMessage("Maximum number of masks reached.")
        return

    new_num_masks = cur_num_masks + 1
    node.parm("masks").set(new_num_masks)


def clear_masks(node: hou.Node):
    """Clear all masks by setting the masks multiparm list to 0.

    Args:
        node (hou.node): current HDA
    """
    node.parm("masks").set(0)


def remove_mask(node: hou.Node, index: str):
    """Remove the selected mask and update the masks multiparm list on the node.

    Args:
        node (hou.node): current HDA
    """
    node.parm("masks").removeMultiParmInstance(int(index) - 1)

    # Update the object merge nodes
    update_object_merge_nodes(node)


def update_object_merge_nodes(node: hou.Node, index: str = None):
    """Update the object merge nodes to match the current number of masks.

    Args:
        node (hou.node): current HDA
        index (str, optional): specific mask index to update. Defaults to None.
    """
    indices = get_indices(node, index)
    check_for_repeated_object_nodes(node, indices)
    if index:
        indices = [index]

    for idx in indices:
        update_selected_objmerge_node(node, idx)


def get_indices(node: hou.Node, index: str = None):
    """Get the list of indices to update.

    Args:
        node (hou.node): current HDA
        index (str, optional): specific mask index to update. Defaults to None.

    Returns:
        list: List of indices to update.
    """
    max_num_masks = 8
    all_indices = [str(i + 1) for i in range(max_num_masks)]

    return all_indices


def check_for_repeated_object_nodes(node: hou.Node, indices: list):
    """Check if any object nodes are repeated and issue a warning if they are.

    Args:
        node (hou.node): current HDA
        indices (list): List of indices to check.
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
    """Update the object merge node for a specific index.

    Args:
        node (hou.node): current HDA
        idx (str): specific mask index to update.
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


def get_render_data(node: hou.Node) -> dict:
    """Get the data required for rendering using playbook.

    Args:
        node (hou.Node): current HDA
    """
    data = {}
    workflow_parm = node.parm("workflow")
    workflow = workflow_parm.menuItems()[workflow_parm.eval()]

    base_model_parm = node.parm("base_model")
    base_model = base_model_parm.menuItems()[base_model_parm.eval()]

    style_parm = node.parm("style")
    style = style_parm.menuItems()[style_parm.eval()]

    scene_prompt = node.evalParm("scene_prompt")

    structure_strength = node.evalParm("structure_strength")

    number_of_masks = node.evalParm("masks")

    # Create a mask prompt string variable for every mask
    mask_prompts = []
    for i in range(number_of_masks):
        mask_prompts.append(node.evalParm(f"mask_prompt{i+1}"))
    
    # mask prompts should be a list of strings. The list should be of length 7. If it's not, pad it with empty strings
    if len(mask_prompts) < 7:
        mask_prompts = mask_prompts + [""] * (7 - len(mask_prompts))
    
    mask_colors = ["ffe906", "0589d6", "a2d4d5", "000016", "00ad58", "f084cf", "ee9e3e"]

    data = {
        "workflow": workflow,
        "base_model": base_model,
        "style": style,
        "scene_prompt": scene_prompt,
        "structure_strength": structure_strength,
        "number_of_masks": number_of_masks,
        "mask_prompts": mask_prompts,
        "mask_colors": mask_colors
    }

    
    return data

    
def render(node):
    """Render the scene using playbook.

    Args:
        node (hou.node): current HDA
    """
    print("Rendering...")
    # TODO: Save the render passes

    # Get the render data from the HDA
    data = get_render_data(node)
    print(data)

    # Create an instance of the ComfyDeployClient class
    client = ComfyDeployClient()

    # TODO : What is the information I need to send?
    client.save_image("test_mask", "mask")
    client.save_image("test_depth", "depth")
    client.save_image("test_outline", "outline")

    # Create the required settings objects
    global_settings = GlobalRenderSettings(
        workflow=data["workflow"],
        base_model=data["base_model"],
        style=data["style"],
        render_mode=0,
    )

    retexture_settings = RetextureRenderSettings(
    prompt=data["scene_prompt"],
    structure_strength=data["structure_strength"],
    mask1=MaskData(prompt=data["mask_prompts"][0], color=data["mask_colors"][0]),
    mask2=MaskData(prompt=data["mask_prompts"][1], color=data["mask_colors"][1]),
    mask3=MaskData(prompt=data["mask_prompts"][2], color=data["mask_colors"][2]),
    mask4=MaskData(prompt=data["mask_prompts"][3], color=data["mask_colors"][3]),
    mask5=MaskData(prompt=data["mask_prompts"][4], color=data["mask_colors"][4]),
    mask6=MaskData(prompt=data["mask_prompts"][5], color=data["mask_colors"][5]),
    mask7=MaskData(prompt=data["mask_prompts"][6], color=data["mask_colors"][6]),
)

    style_transfer_settings = StyleTransferRenderSettings(
        prompt = data["scene_prompt"],
        style_transfer_strength=data["structure_strength"]
    )

    # Call the run_workflow function
    result = client.run_workflow(global_settings, retexture_settings, style_transfer_settings)

    # Process the result
    print(result)


