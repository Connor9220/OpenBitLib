#!/usr/bin/env python3

import sqlite3
import os
import qrcode
from io import BytesIO
import requests
import hashlib
import json
from fractions import Fraction
import re
from settings import load_config
from db_utils import *
from generate_manifest import main as generate_manifest_main
from fixtool import main as merge_tool_tables

# Load the configuration
config = load_config()

# Access settings
wiki_username = config["wiki_credentials"]["username"]
wiki_password = config["wiki_credentials"]["password"]
qr_images_location = config["file_paths"]["qr_images_location"]

# Initialize DB_MODE - Add this section
API_URL = config.get("api", {}).get("url", "http://127.0.0.0:8000")
DB_MODE = config.get("api", {}).get("mode", "direct")
set_db_mode(DB_MODE, API_URL)  # This will initialize the DB_MODE in db_utils


def sanitize_filename(name):
    """
    Sanitize the tool name for use as a filename:

    - Replaces special characters (e.g., /, \, :, *, ?, <, >, |) with underscores.
    - Converts " to in.
    - Strips leading and trailing whitespace.

    Args:
        name (str): The original tool name to sanitize.

    Returns:
        str: A sanitized string safe for use as a filename.
    """
    if not name:
        return ""

    # Replace " with "in"
    name = name.replace('"', "in")

    # Replace any non-alphanumeric, non-space, and non-period characters with underscores
    clean_name = re.sub(r'[<>:"/\\|?*\n\r]+', "_", name)

    return clean_name.strip()


def get_shape_type(shape_name):
    """
    Convert shape name from v1.0 format (with .fcstd extension) to v1.1/v1.2 format (without extension).
    Capitalizes the shape name and handles special case for v-bit -> VBit.

    Args:
        shape_name (str): The shape name (e.g., "endmill.fcstd")

    Returns:
        str: The capitalized shape type without extension (e.g., "Endmill")
    """
    if not shape_name:
        return shape_name

    # Remove .fcstd extension if present
    if shape_name.endswith(".fcstd"):
        shape_name = shape_name[:-6]

    # Special case for v-bit
    if shape_name.lower() == "v-bit":
        return "VBit"

    # Capitalize the shape name
    return shape_name.capitalize()


def get_version_paths(version):
    """
    Generate file paths for a specific FreeCAD version based on base directory.

    Args:
        version (str): Version identifier (e.g., "v1-0", "v1-1", "v1-2")

    Returns:
        dict: Dictionary with 'bits_dir' and 'library_path' keys
    """
    base_dir = config["file_paths"]["base_directory"]
    library_name = config["freecad"]["library_name"]

    if version == "v1-0":
        # v1.0 uses Tools/Bit/ structure
        bits_dir = os.path.join(base_dir, "Tools", "Bit")
        library_path = os.path.join(base_dir, "Tools", "Library", library_name)
    else:
        # v1.1+ uses CAMAssets/v1-x/Tools/Bit/ structure
        bits_dir = os.path.join(base_dir, "CAMAssets", version, "Tools", "Bit")
        library_path = os.path.join(
            base_dir, "CAMAssets", version, "Tools", "Library", library_name
        )

    return {"bits_dir": bits_dir, "library_path": library_path}


def format_measurement(value, convert_to_fraction=False, add_quotes=False):
    """
    Format measurements for consistent wiki output:

    - Converts values to fractional inches if `convert_to_fraction=True`.
    - Adds quotes for inches if `add_quotes=True`.
    - Leaves metric values untouched unless conversion is specified.

    Args:
        value (str): The measurement value to format (e.g., "5in", "12.7mm").
        convert_to_fraction (bool): Whether to convert inches to fractional format.
        add_quotes (bool): Whether to append quotes for inch values.

    Returns:
        str: The formatted measurement, or "N/A" for invalid input.
    """
    if value is None or value.strip() == "":
        return "N/A"

    try:
        # Normalize the input (e.g., "5in" -> "5 in", "5" -> "5 in")
        match = re.match(r"^([\d\.]+)\s*([a-zA-Z\"']*)$", value.strip())
        if not match:
            return value  # Return as-is if it doesn't match expected formats

        num_str, unit = match.groups()

        # Default to "in" if no unit is provided
        if unit in ('"', ""):
            unit = "in"

        # Convert numeric part to float for calculations, but keep the original string
        num = float(num_str)

        if unit == "in":
            if convert_to_fraction:
                # Convert to fraction, but keep whole numbers intact
                if num.is_integer():
                    formatted_value = f"{int(num)}"
                else:
                    fraction = Fraction(num).limit_denominator(64)
                    if fraction.numerator > fraction.denominator:
                        # Mixed fraction format
                        whole = fraction.numerator // fraction.denominator
                        remainder = fraction.numerator % fraction.denominator
                        formatted_value = (
                            f"{whole}-{remainder}/{fraction.denominator}"
                            if remainder > 0
                            else f"{whole}"
                        )
                    else:
                        # Proper fraction
                        formatted_value = f"{fraction.numerator}/{fraction.denominator}"
            else:
                # Keep the original value as-is (retain decimal places from input)
                formatted_value = num_str

            # Handle quotes if needed
            if add_quotes:
                return f'{formatted_value}"'
            else:
                return f"{formatted_value} in"

        elif unit == "mm":
            # Keep metric values untouched
            return value

        else:
            # Return unprocessed for unknown or unsupported units
            return value

    except ValueError:
        return value  # If invalid format, return as-is


def extract_numeric_value_with_unit(value):
    """
    Extract the numeric part and unit from a value.

    Handles formats like:
    - "12.34 in", "45.67mm", "89.01\""
    - Returns a tuple (float, str) where the float is the numeric part,
      and the string is the detected unit (defaulting to "in" if not found).

    Args:
        value (str): The input value as a string.

    Returns:
        tuple: (numeric_value: float, unit: str)
    """
    if not value or not isinstance(value, str):
        return 0.0, "in"  # Default to inches if invalid

    # Match numeric part and optional unit
    match = re.match(r"^([\d\.]+)\s*([a-zA-Z\"']*)$", value.strip())
    if match:
        numeric_value = float(match.group(1))
        unit = match.group(2).strip() or "in"  # Default to inches if no unit
        return numeric_value, unit
    return 0.0, "in"  # Default to 0.0 inches if parsing fails


def convert_to_original_unit(value, unit):
    """
    Convert a value to its original unit.

    Supports conversion between millimeters (mm) and inches (in).

    Args:
        value (float): The numeric value to convert.
        unit (str): The target unit ("mm" or "in").

    Returns:
        str: The converted value with the original unit appended.
    """
    if unit == "mm":
        return f"{value * 25.4:.3f} mm"  # Inches to millimeters
    elif unit == "in":
        return f"{value:.4f} in"  # Keep in inches
    else:
        return f"{value:.4f} {unit}"  # Default for unknown units


def map_tool_to_json(tool, columns, version="v1-0"):
    """
    Map tool data from the database to a JSON structure.

    Dynamically maps database column values to JSON fields based on the tool's shape
    and required parameters.

    Args:
        tool (dict): A dictionary representing the tool data from the database.
        columns (list): A list of column names corresponding to the tool data.
        version (str): FreeCAD version format (v1-0, v1-1, v1-2, etc.).

    Returns:
        dict: A dictionary in JSON format representing the tool.
    """
    # Use tool directly as a dictionary
    tool_data_dict = tool

    # Extract shape_type from Tools.Shape field
    shape_type = tool_data_dict.get("Shape", "unknown")

    # Look up the ShapeName (filename) from FCShapes using shape_type
    shape_data = fetch_shapes_by_type(shape_type)
    if not shape_data:
        print(f"Shape type '{shape_type}' not found in FCShapes.")
        json_data = {
            "version": 2,
            "name": tool_data_dict.get("ToolName", "Unnamed Tool"),
            "shape": shape_type,
            "parameter": {"Shape": shape_type},
            "attribute": {},
        }
        return json_data

    # Get the filename from ShapeName field
    shape_name = shape_data.ShapeName

    # Prepare JSON structure with shape_name as the filename
    json_data = {
        "version": 2,
        "name": tool_data_dict.get("ToolName", "Unnamed Tool"),
        "shape": shape_name,
        "parameter": {},
        "attribute": {},
    }

    # Parse ShapeParameter and ShapeAttribute from the database
    shape_parameters_list = json.loads(shape_data.ShapeParameter or "[]")
    shape_attributes_list = json.loads(shape_data.ShapeAttribute or "[]")

    # Retrieve JSON values stored in the database
    shape_parameters_values = json.loads(
        tool_data_dict.get("ShapeParameter", "{}") or "{}"
    )
    shape_attributes_values = json.loads(
        tool_data_dict.get("ShapeAttribute", "{}") or "{}"
    )

    # Special case: Handle bullnose.fcstd shape
    if shape_name == "bullnose.fcstd" and version == "v1-0":
        # v1.0: Calculate FlatRadius from CornerRadius
        try:
            # Extract numeric values and units
            diameter, diameter_unit = extract_numeric_value_with_unit(
                tool_data_dict.get("ToolDiameter", "0")
            )
            corner_radius_value = shape_parameters_values.get("CornerRadius", "0")
            corner_radius, corner_radius_unit = extract_numeric_value_with_unit(
                corner_radius_value
            )

            # Ensure both units are consistent
            if diameter_unit != corner_radius_unit:
                raise ValueError(
                    f"Unit mismatch: {diameter_unit} vs {corner_radius_unit}"
                )

            # Calculate FlatRadius
            flat_radius = (diameter / 2) - corner_radius
            json_data["parameter"]["FlatRadius"] = convert_to_original_unit(
                flat_radius, diameter_unit
            )
        except (ValueError, TypeError) as e:
            print(f"Invalid data for calculating FlatRadius: {e}")

    # Populate parameters: Iterate through the list
    for param in shape_parameters_list:
        if (
            param == "CornerRadius"
            and shape_name == "bullnose.fcstd"
            and version == "v1-0"
        ):
            # Skip CornerRadius for v1.0 bullnose (we use calculated FlatRadius instead)
            continue

        db_param = map_column_names(
            param, direction="to_sqlite"
        )  # Convert to SQLite name for direct fields
        value = tool_data_dict.get(db_param, shape_parameters_values.get(param, None))
        json_data["parameter"][param] = value

    # Populate attributes: Prioritize direct fields
    for attr in shape_attributes_list:
        db_attr = map_column_names(
            attr, direction="to_sqlite"
        )  # Convert to SQLite name for direct fields
        value = tool_data_dict.get(db_attr, shape_attributes_values.get(attr, None))
        json_data["attribute"][attr] = value

    return json_data


def map_column_names(param, direction="to_json"):
    """
    Map column names between SQLite and JSON parameter names.

    Args:
        param (str): The column name to map.
        direction (str): The mapping direction:
                         - "to_json" for SQLite-to-JSON mapping.
                         - "to_sqlite" for JSON-to-SQLite mapping.

    Returns:
        str: The corresponding mapped name, or the original param if no mapping exists.
    """
    mapping = {
        "Diameter": "ToolDiameter",
        "Length": "OAL",
        "CuttingEdgeHeight": "LOC",
        "Material": "ToolMaterial",
        "ShankDiameter": "ToolShankSize",
    }

    if direction == "to_sqlite":
        return mapping.get(param, param)
    elif direction == "to_json":
        reverse_mapping = {v: k for k, v in mapping.items()}
        return reverse_mapping.get(param, param)
    else:
        raise ValueError(
            f"Invalid direction: {direction}. Use 'to_json' or 'to_sqlite'."
        )


# Convert string values that represent integers to actual integers
def convert_string_to_int(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, dict) or isinstance(value, list):
                convert_string_to_int(value)
            elif isinstance(value, str):
                # Only convert if the string represents an integer
                if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                    obj[key] = int(value)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, dict) or isinstance(item, list):
                convert_string_to_int(item)
            elif isinstance(item, str):
                if item.isdigit() or (item.startswith("-") and item[1:].isdigit()):
                    obj[i] = int(item)


def generate_json_files(tool_data, columns, output_directory, version="v1-0"):
    """
    Generate JSON files for tools in specified FreeCAD version format.

    Args:
        tool_data (list of tuples): Tool data fetched from the database.
        columns (list): Column names corresponding to the tool data.
        output_directory (str): Directory where the JSON files will be saved.
        version (str): FreeCAD version format (v1-0, v1-1, v1-2, etc.)

    Version differences:
        - v1-0: Separate 'parameter' and 'attribute' sections, 'shape' field with .fcstd extension
        - v1-1: All in 'parameter' section, 'shape-type' field without .fcstd extension (capitalized),
                adds 'id' field (filename without extension), removes SpindlePower
        - v1-2: Same as v1-1 but adds 'units' field at root level (Imperial or Metric)

    Returns:
        None
    """
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # Process each tool
    for tool in tool_data:
        tool_json = map_tool_to_json(tool, columns, version)

        # Handle version-specific formatting
        if version == "v1-0":
            # v1.0 keeps the original format with separate parameter/attribute sections
            # and 'shape' field with .fcstd extension
            # Special handling: translate 'radius.fcstd' to 'roundover.fcstd' for v1.0
            if tool_json.get("shape") == "radius.fcstd":
                tool_json["shape"] = "roundover.fcstd"
        else:
            # v1.1+ formats: Move all attributes into parameters
            if "attribute" in tool_json and tool_json["attribute"]:
                tool_json["parameter"].update(tool_json["attribute"])
                tool_json["attribute"] = {}

            # Use shape_type from database for v1.1+
            if "shape" in tool_json:
                tool_json["shape-type"] = tool.get("Shape", "unknown")

            # v1.2+ adds units field in parameter section
            if version == "v1-2":
                units = tool.get("Units") if "Units" in columns else None
                tool_json["parameter"]["Units"] = units if units else "Imperial"

        convert_string_to_int(tool_json)

        tool_name = tool_json["name"]
        sanitized_tool_name = sanitize_filename(tool_name)

        if version != "v1-0":
            tool_json["id"] = sanitized_tool_name

        output_file = os.path.join(output_directory, f"{sanitized_tool_name}.fctb")

        with open(output_file, "w", encoding="utf-8") as json_file:
            json.dump(tool_json, json_file, sort_keys=True, indent=2)
            json_file.write("\n")
        print(f"Generated {version} JSON file: {output_file}")


def get_image_hash(file_path):
    """
    Compute the SHA-256 hash of a file.

    Reads the file in chunks to compute its SHA-256 hash, which is used to
    verify if the file has changed.

    Args:
        file_path (str): The path to the file for which the hash is to be computed.

    Returns:
        str: The SHA-256 hash of the file as a hexadecimal string.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def make_anchor(header):
    # Replace spaces and slashes with a single underscore, collapse multiple underscores
    anchor = re.sub(r"[ /]+", "_", header)
    return anchor


def generate_index_page_content():
    """
    Generate the main index page content for all tools with their numbers and names,
    grouped by tool type headers, with a bookmark index at the top.
    """
    # Fetch tool numbers and names
    tools = fetch_tool_numbers_and_details()

    # Get index page and prefix from configuration
    index_page = config["wiki_settings"]["index_page"]
    page_prefix = config["wiki_settings"]["page_prefix"]

    # Define tool group headers and their ranges
    tool_groups = [
        ((10, 19), "V-bits / Engraving"),
        ((20, 29), "Upcut Endmills"),
        ((30, 39), "Downcut Endmills"),
        ((40, 49), "Compression Endmills"),
        ((50, 59), "Ballnose Endmills"),
        ((60, 69), "Surfacing Bits"),
        ((70, 79), "Bowl & Tray"),
        ((80, 89), "Roundover / Form Tools"),
        ((90, 99), "Specialty Tools"),
        ((101, 109), "Drill Bits"),
    ]

    # Sort tools by ToolNumber
    tools_sorted = sorted(tools, key=lambda t: int(t["ToolNumber"]))

    # --- Create bookmarks/index at the top ---
    bookmark_lines = ["===Tool Groups==="]
    bookmark_lines.append('<span id="top"></span>\n')
    for (start, end), header in tool_groups:
        anchor = make_anchor(header)
        bookmark_lines.append(f"[[#{anchor}|T{start}–T{end} / {header}]]<br>")
    bookmark_lines.append("")  # Blank line after bookmarks

    # --- Create grouped tool lists with anchors ---
    output_lines = []
    for (start, end), header in tool_groups:
        anchor = make_anchor(header)
        group_tools = [
            tool for tool in tools_sorted if start <= int(tool["ToolNumber"]) <= end
        ]
        if group_tools:
            output_lines.append(f"\n<span id=\"{anchor}\"></span>\n'''{header}'''")
            for tool in group_tools:
                output_lines.append(
                    f"*[[{index_page}/{page_prefix} {tool['ToolNumber']}|Tool {tool['ToolNumber']} - {tool['ToolName']}]]"
                )
            output_lines.append("[[#Top|[Top]]]\n")  # Blank line between groups

    return "\n".join(bookmark_lines + output_lines)


def generate_tools_json(output_path=None, version="v1-0"):
    """
    Generate a JSON file containing tool numbers and paths to their .fctb files.

    Args:
        output_path (str, optional): Path to save the generated JSON file.
                                     Defaults to the library file location from config.
        version (str): FreeCAD version ("v1-0", "v1-1", or "v1-2")

    Returns:
        None
    """
    # Determine output path based on version if not provided
    if output_path is None:
        paths = get_version_paths(version)
        output_path = paths["library_path"]

    # Fetch tool numbers and names
    tools = fetch_tool_numbers_and_details()

    # Create the JSON structure
    tools_data = {"tools": [], "version": 1}
    for tool in tools:
        tool_name = tool["ToolName"]
        if tool_name:  # Ensure the tool has a name
            sanitized_name = sanitize_filename(tool_name)
            file_path = f"{sanitized_name}.fctb"
            tools_data["tools"].append({"nr": tool["ToolNumber"], "path": file_path})

    # Write to the output file
    with open(output_path, "w") as json_file:
        json.dump(tools_data, json_file, indent=2)
    print(f"Generated library file {version}: {output_path}")


def create_session(api_url, username, password):
    """
    Create and return a session for MediaWiki API after logging in.

    Authenticates with the MediaWiki API using the provided credentials and
    returns the session for further API interactions.

    Args:
        api_url (str): The API endpoint URL for the MediaWiki instance.
        username (str): The username for the MediaWiki API.
        password (str): The password for the MediaWiki API.

    Returns:
        requests.Session: An authenticated session for MediaWiki API calls.
    """
    session = requests.Session()
    login_token_response = session.get(
        api_url,
        params={"action": "query", "format": "json", "meta": "tokens", "type": "login"},
    )
    login_token = login_token_response.json()["query"]["tokens"]["logintoken"]

    response = session.post(
        api_url,
        data={
            "action": "login",
            "lgname": username,
            "lgpassword": password,
            "lgtoken": login_token,
            "format": "json",
        },
    )
    if response.json().get("login", {}).get("result") != "Success":
        raise Exception("Failed to log in to MediaWiki API")
    return session


def upload_image(session, api_url, file_path, file_name):
    """
    Upload an image file to MediaWiki.

    Sends an image file to the MediaWiki API for upload. Supports overwriting
    existing files.

    Args:
        session (requests.Session): The authenticated session for MediaWiki API.
        api_url (str): The API endpoint URL for the MediaWiki instance.
        file_path (str): The path to the image file to upload.
        file_name (str): The name of the file as it should appear on the wiki.

    Returns:
        dict: The response JSON from the MediaWiki API.
    """
    edit_token_response = session.get(
        api_url,
        params={"action": "query", "meta": "tokens", "type": "csrf", "format": "json"},
    )
    edit_token = edit_token_response.json()["query"]["tokens"]["csrftoken"]

    with open(file_path, "rb") as file:
        files = {"file": (file_name, file.read())}
        data = {
            "action": "upload",
            "filename": file_name,
            "token": edit_token,
            "format": "json",
            "ignorewarnings": "true",  # This allows overwriting existing files
        }
        response = session.post(api_url, files=files, data=data)
        return response.json()


def upload_image_if_changed(session, api_url, file_path, file_name, tool_number):
    """
    Upload an image to MediaWiki only if it has changed and the file exists.

    Args:
        session (requests.Session): The authenticated session for MediaWiki API.
        api_url (str): The API endpoint URL for the MediaWiki instance.
        file_path (str): Path to the image file to check and upload.
        file_name (str): Name of the file on the wiki.
        tool_number (int): The tool number associated with the image.

    Returns:
        None
    """
    # Check if the file exists
    if not os.path.exists(file_path):
        print(f"Image file not found: {file_path}. Skipping upload.")
        return

    # Compute the current hash of the image
    current_hash = get_image_hash(file_path)

    # Fetch the stored hash
    stored_hash = fetch_image_hash(tool_number)

    update_image_hash(tool_number, current_hash)

    # Compare hashes and upload if they differ
    if current_hash != stored_hash:
        response = upload_image(session, api_url, file_path, file_name)
        if response.get("upload", {}).get("result") == "Success":
            print(f"Image {file_name} uploaded and hash updated.")
        else:
            print(f"Failed to upload image {file_name}: {response}")
    else:
        print(f"Image {file_name} unchanged. No upload needed.")


def upload_wiki_page(session, api_url, page_title, content):
    """
    Upload or update a wiki page using the MediaWiki API.

    Sends the provided content to the specified page title on the MediaWiki
    instance. Supports creating or overwriting existing pages.

    Args:
        session (requests.Session): The authenticated session for MediaWiki API.
        api_url (str): The API endpoint URL for the MediaWiki instance.
        page_title (str): The title of the wiki page to upload or update.
        content (str): The content to upload to the wiki page.

    Returns:
        dict: The response JSON from the MediaWiki API.
    """
    edit_token_response = session.get(
        api_url, params={"action": "query", "meta": "tokens", "format": "json"}
    )
    edit_token = edit_token_response.json()["query"]["tokens"]["csrftoken"]

    response = session.post(
        api_url,
        data={
            "action": "edit",
            "title": page_title,
            "text": content,
            "token": edit_token,
            "format": "json",
        },
    )
    return response.json()


def generate_qr_code(tool_number, base_url=None):
    """
    Generate a QR code for a tool and save it as a PNG file.

    Creates a QR code linking to the tool's wiki page and saves it to the
    configured directory. If the QR code content hasn't changed, skips regeneration.

    Args:
        tool_number (int): The tool number to generate the QR code for.
        base_url (str, optional): The base URL for tool links. Defaults to the
                                  base URL in config.

    Returns:
        str: The file path of the saved QR code.
    """
    base_url = base_url or config["qr_code_settings"].get("base_url", "")
    qr_data = f"{base_url}/tool_{tool_number}"
    qr_file_name = os.path.join(
        config["file_paths"]["qr_images_location"], f"tool_{tool_number}_qr.png"
    )

    # Generate the QR code
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    new_img = qr.make_image(fill_color="black", back_color="white")
    temp_buffer = BytesIO()
    new_img.save(temp_buffer, format="PNG")
    temp_buffer.seek(0)
    new_data = temp_buffer.read()

    # Check if the file exists and compare its content
    if os.path.exists(qr_file_name):
        with open(qr_file_name, "rb") as existing_file:
            existing_data = existing_file.read()
        if existing_data == new_data:
            print(
                f"QR code for tool {tool_number} has not changed, skipping regeneration."
            )
            return qr_file_name

    # Save the new QR code
    with open(qr_file_name, "wb") as file:
        file.write(new_data)
    print(f"QR code saved as {qr_file_name}")
    return qr_file_name


def delete_wiki_item(session, api_url, title, is_media=False):
    """
    Delete a wiki page or media file using the MediaWiki API.

    Removes the specified page or media file from the MediaWiki instance.
    Handles errors and ensures proper authentication.

    Args:
        session (requests.Session): The authenticated session for MediaWiki API.
        api_url (str): The API endpoint URL for the MediaWiki instance.
        title (str): The title of the page or the name of the media file (e.g., "File:filename").
        is_media (bool): Set to True if deleting a media file. Defaults to False.

    Returns:
        dict: The response JSON from the MediaWiki API.
    """
    try:
        # Fetch edit token
        token_response = session.get(
            api_url, params={"action": "query", "meta": "tokens", "format": "json"}
        )
        token_response.raise_for_status()  # Raise an error for HTTP issues
        edit_token = (
            token_response.json()
            .get("query", {})
            .get("tokens", {})
            .get("csrftoken", None)
        )

        if not edit_token:
            raise ValueError(
                "Failed to retrieve CSRF token for deleting the wiki item."
            )

        # Prepare the title for deletion
        if is_media:
            title = f"File:{title}"

        # Perform the delete action
        delete_params = {
            "action": "delete",
            "title": title,
            "token": edit_token,
            "format": "json",
        }
        response = session.post(api_url, data=delete_params)
        response.raise_for_status()  # Raise an error for HTTP issues
        response_data = response.json()

        # Check for errors in the response
        if "error" in response_data:
            error_message = response_data["error"].get("info", "Unknown error")
            raise ValueError(f"Failed to delete '{title}': {error_message}")

        return response_data

    except requests.exceptions.RequestException as http_err:
        print(f"HTTP error occurred while deleting '{title}': {http_err}")
        raise
    except Exception as e:
        print(f"Error occurred while deleting '{title}': {e}")
        raise


def protect_wiki_page(session, api_url, page_title):
    """
    Protect a wiki page from being edited by non-admin users.

    Uses the MediaWiki API to set protection levels for the specified page,
    ensuring only sysops can edit or move it.

    Args:
        session (requests.Session): The authenticated session for MediaWiki API.
        api_url (str): The API endpoint URL for the MediaWiki instance.
        page_title (str): The title of the wiki page to protect.

    Returns:
        dict: The response JSON from the MediaWiki API.
    """
    # Fetch edit token
    token_response = session.get(
        api_url, params={"action": "query", "meta": "tokens", "format": "json"}
    )
    edit_token = token_response.json()["query"]["tokens"]["csrftoken"]

    # Set protection parameters
    protection_params = {
        "action": "protect",
        "title": page_title,
        "token": edit_token,
        "protections": "edit=sysop|move=sysop",  # Only sysops can edit/move
        "format": "json",
    }
    response = session.post(api_url, data=protection_params)
    return response.json()


def generate_wiki_page(tool_data):
    """
    Generate wiki page content for a tool using the provided data.
    """
    template = """
[[Nibblerbot/tools|Back to Tool Library]]
==Tool [ToolNumber] - [ToolName]==
{| class="wikitable"
|-
!style="width: 200px;"| Attribute !!style="width: 400px;"| Details
|-
| '''Tool #''' || [ToolNumber]
|-
| '''Tool Type''' || [ToolType]
|-
| '''Shank Size''' || [ToolShankSize]
|-
| '''Diameter''' || [ToolDiameter]
[INSERT_CORNERRADIUS][INSERT_CUTTINGRADIUS][INSERT_TAPERANGLE][INSERT_TAPERDIAMETER]|-
| '''Flutes (FL)''' || [Flutes]
|-
| '''Overall Length (OAL)''' || [OAL]
|-
| '''Length of Cut (LOC)''' || [LOC]
|-
| '''Max RPM''' || [ToolMaxRPM]
|-
| '''Material''' || [ToolMaterial]
|-
| '''Coating''' || [ToolCoating]
|-
| '''Part Number''' || [PartNumber]
|-
| '''Manufacturer''' || [ManufacturerName]
|-
| '''Image''' || [[File:[ToolImageFileName]|thumb|left]]
|-
| '''Order Link''' || [[[ToolOrderURL] Click here to purchase this tool]]
|}

==Usage Information==
'''Compatible Materials''': [Materials]

'''Recommended Speeds and Feeds''':
 '''RPM''': [SuggestedRPM]
 '''Feed Rate''': [SuggestedFeedRate]
 '''Depth of Cut''': [SuggestedMaxDOC]

==Additional Notes==
[AdditionalNotes]"""

    # Parse ShapeParameter from tool_data
    shape_parameters = json.loads(tool_data.get("ShapeParameter", "{}") or "{}")

    # Add CornerRadius if present and format it
    corner_radius = shape_parameters.get("CornerRadius")
    if corner_radius:
        formatted_corner_radius = format_measurement(
            corner_radius, convert_to_fraction=True, add_quotes=True
        )
        corner_radius_row = f"|-\n| '''Corner Radius''' || {formatted_corner_radius}\n"
    else:
        corner_radius_row = ""

    # Add CuttingRadius if present and format it
    cutting_radius = shape_parameters.get("CuttingRadius")
    if cutting_radius:
        formatted_cutting_radius = format_measurement(
            cutting_radius, convert_to_fraction=True, add_quotes=True
        )
        cutting_radius_row = (
            f"|-\n| '''Cutting Radius''' || {formatted_cutting_radius}\n"
        )
    else:
        cutting_radius_row = ""

    # Add TaperAngle if present and format it
    taper_angle = shape_parameters.get("TaperAngle")
    if taper_angle:
        formatted_taper_angle = format_measurement(
            taper_angle, convert_to_fraction=True, add_quotes=True
        )
        taper_angle_row = f"|-\n| '''Taper Angle''' || {formatted_taper_angle}\n"
    else:
        taper_angle_row = ""

    # Add TaperDiameter if present and format it
    taper_diameter = shape_parameters.get("TaperDiameter")
    if taper_diameter:
        formatted_taper_diameter = format_measurement(
            taper_diameter, convert_to_fraction=True, add_quotes=True
        )
        taper_diameter_row = (
            f"|-\n| '''Taper Diameter''' || {formatted_taper_diameter}\n"
        )
    else:
        taper_diameter_row = ""

    placeholders = [
        "ToolNumber",
        "ToolName",
        "ToolType",
        "ToolShankSize",
        "Flutes",
        "OAL",
        "LOC",
        "ToolMaxRPM",
        "ToolDiameter",
        "ToolMaterial",
        "ToolCoating",
        "PartNumber",
        "ManufacturerName",
        "ToolOrderURL",
        "Materials",
        "SuggestedRPM",
        "SuggestedMaxDOC",
        "AdditionalNotes",
        "SuggestedFeedRate",
        "ToolImageFileName",
    ]

    page_content = template

    # Replace placeholders in the template
    page_content = page_content.replace("[INSERT_CORNERRADIUS]", corner_radius_row)
    page_content = page_content.replace("[INSERT_CUTTINGRADIUS]", cutting_radius_row)
    page_content = page_content.replace("[INSERT_TAPERANGLE]", taper_angle_row)
    page_content = page_content.replace("[INSERT_TAPERDIAMETER]", taper_diameter_row)

    for field in placeholders:
        value = tool_data.get(field, None)  # Access value using dictionary key

        # Handle specific formatting for certain fields
        if field == "ToolMaxRPM":
            formatted_value = "N/A" if str(value) == "-1" else f"{int(value):,}"
        elif field in ["ToolShankSize", "ToolDiameter"]:
            formatted_value = format_measurement(
                value, convert_to_fraction=True, add_quotes=True
            )
        elif field in ["OAL", "LOC"]:
            formatted_value = format_measurement(value, add_quotes=True)
        elif field == "ToolImageFileName":
            formatted_value = (
                str(value)
                if value
                else f"tool_{tool_data.get('ToolNumber', 'unknown')}.png"
            )
        else:
            formatted_value = str(value) if value else "N/A"

        # Replace the placeholder in the page content
        page_content = page_content.replace(f"[{field}]", formatted_value)

    return page_content


def main(return_session=False, tool_number=None, progress_callback=None):
    """
    Main function to handle publishing tools to the wiki with optional progress updates.

    Manages tool publishing operations, including generating JSON files,
    uploading wiki pages, handling images, and updating the index page.

    Args:
        return_session (bool, optional): If True, returns an authenticated session
                                         without performing any publishing.
        tool_number (int, optional): The specific tool number to process. If None,
                                     processes all tools.
        progress_callback (function, optional): A callback function to update progress.
                                                Accepts an integer progress value (0-100).

    Returns:
        dict: A dictionary containing the status of the operation and any messages.
    """
    api_url = config["wiki_settings"]["api_url"]
    username = config["wiki_credentials"]["username"]
    password = config["wiki_credentials"]["password"]

    # Get configured FreeCAD versions
    versions = config["freecad"]["versions"]

    session = create_session(api_url, username, password)

    if return_session:
        return session

    # try:
    if tool_number is None:
        # Process all tools
        tool_data, columns = fetch_tool_data()
    else:
        # Process a specific tool
        tool_data, columns = fetch_tool_data(tool_number=tool_number)

    total_tools = len(tool_data)
    for idx, tool in enumerate(tool_data):
        # Calculate and send progress (wiki publishing is 90%, file generation adds on top)
        if progress_callback:
            percentage = int(
                (idx + 1) / total_tools * 80
            )  # Reserve 20% for other tasks
            progress_callback(percentage)

        # Generate JSON files for all configured FreeCAD versions
        for version in versions:
            paths = get_version_paths(version)
            generate_json_files([tool], columns, paths["bits_dir"], version)

        # Publish tool to the wiki
        tool_number = tool["ToolNumber"]
        wiki_content = generate_wiki_page(tool)
        page_title = f"{config['wiki_settings']['index_page']}/{config['wiki_settings']['page_prefix']}_{tool_number}"
        upload_response = upload_wiki_page(session, api_url, page_title, wiki_content)

        # Handle image upload if needed
        image_file_name = tool.get("ToolImageFileName") or f"tool_{tool_number}.png"
        image_file_path = os.path.join(
            config["file_paths"]["bit_images"], image_file_name
        )

        if os.path.exists(image_file_path):
            upload_image_if_changed(
                session, api_url, image_file_path, image_file_name, tool_number
            )

        # Generate QR code
        generate_qr_code(tool_number)

    # Update the index page
    index_page_content = generate_index_page_content()
    upload_wiki_page(
        session, api_url, config["wiki_settings"]["index_page"], index_page_content
    )

    # Generate consolidated JSON library files for all configured versions
    for version in versions:
        generate_tools_json(version=version)

    # Update the manifest after publishing
    manifest_dir = config.get("manifest_settings", {}).get(
        "manifest_dir", "../NibblerBOT/Manifest/"
    )
    manifest_file = config.get("manifest_settings", {}).get(
        "manifest_file", "manifest.json"
    )
    manifest_path = os.path.join(manifest_dir, manifest_file)

    # Use base directory for manifest generation
    base_dir = config["file_paths"]["base_directory"]
    source_dir = os.path.abspath(base_dir)

    try:
        generate_manifest_main(source_dir, manifest_path)
        print(f"Manifest updated at {manifest_path}")
    except Exception as e:
        print(f"Failed to update manifest: {e}")

    # Generate tool table and merge after publishing
    try:
        tool_table_data = generate_tool_table()
        merge_tool_tables(update_data=tool_table_data)
    except Exception as e:
        print(f"Failed to generate or merge tool table: {e}")

    if progress_callback:
        progress_callback(100)

    return {"status": "success", "message": "All tools processed successfully."}

    # except Exception as e:
    #     return {"status": "error", "message": str(e)}


def generate_tool_table():
    """
    Generate tool table data from all tools in the database.

    Format: T<num> P0 X0 Y0 Z0 A0 B0 C0 U<rpm> V0 W0 D<diameter> I0 J0 Q0 ;<name>
    U value is calculated from ToolMaxRPM:
      - If MaxRPM = -1, output U-1
      - If MaxRPM != machine_max_rpm, output U<MaxRPM>
      - Otherwise output U0

    Returns:
        list: List of formatted tool table lines
    """
    # Fetch all tools
    tools, columns = fetch_tool_data()
    
    # Get machine max RPM from config
    machine_max_rpm = config.get("machine_settings", {}).get("max_rpm", 24000)

    lines = []
    for tool in tools:
        tool_number = tool.get("ToolNumber")
        tool_name = tool.get("ToolName", "Unnamed Tool")

        # Get diameter and convert to imperial if needed
        diameter_str = tool.get("ToolDiameter", "0")
        diameter = extract_numeric(diameter_str, field_type="dimension")
        if diameter is None:
            diameter = 0.0
        
        # Calculate U value from ToolMaxRPM
        max_rpm = tool.get("ToolMaxRPM", 0)
        # Remove commas and convert to int for comparison
        try:
            if isinstance(max_rpm, str):
                max_rpm_value = int(max_rpm.replace(",", ""))
            else:
                max_rpm_value = int(max_rpm)
        except (ValueError, TypeError):
            max_rpm_value = 0
        
        # Determine U value based on MaxRPM
        if max_rpm_value == -1:
            u_value = "U-1"
        elif max_rpm_value != machine_max_rpm and max_rpm_value != 0:
            u_value = f"U{max_rpm_value}"
        else:
            u_value = "U0"

        # Format the line
        # T<num> P0 X0 Y0 Z0 A0 B0 C0 U<rpm> V0 W0 D<diameter> I0 J0 Q0 ;<name>
        line = f"T{tool_number} P0 X0 Y0 Z0 A0 B0 C0 {u_value} V0 W0 D{diameter:.4f} I0 J0 Q0 ;{tool_name}"
        lines.append(line)

    return lines


if __name__ == "__main__":
    # Standalone execution
    input_val = input(
        "Enter the tool number or press Enter to process all tools: "
    ).strip()
    tool_number = int(input_val) if input_val else None

    result = main(tool_number=tool_number)

    if result["status"] == "success":
        print("Publishing completed successfully!")
    else:
        print(f"Error: {result['message']}")
