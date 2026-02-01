import re
from settings import load_config

# Load configuration
config = load_config()


# Fixing header detection and preserving U, Z, and D in the correct order
def read_master_file(file_path):
    with open(file_path, "r") as file:
        lines = file.readlines()

    header = None
    data = {}

    # Check if the first line starts with ';', if so treat it as header
    if lines[0].startswith(";"):
        header = lines[0]
        lines = lines[1:]  # Remove the header from the data lines

    # Process the remaining lines as data
    for line in lines:
        tool = line.split()[0]
        data[tool] = line.strip()

    return header, data


# Read updater file and return data in the correct format
def read_updater_file(file_path):
    with open(file_path, "r") as file:
        lines = file.readlines()

    data = {}
    is_extended_format = lines[0].startswith(";")

    for line in lines:
        if is_extended_format:
            if line.startswith(";"):
                continue  # Skip semicolon-only lines
            parts = line.split(";", 1)
            tool_info = parts[0].strip()
            remark = parts[1].strip() if len(parts) > 1 else ""
            tool_data = tool_info.split()
            tool = tool_data[0]
            pocket = tool_data[1][1:]  # Strip 'P'
            diameter_metric = float([x for x in tool_data if x.startswith("D")][0][1:])
        else:
            # Handle both "D0.125;comment" and "D0.125 ;comment" formats
            parts = line.split(";", 1)
            tool_info = parts[0].strip()
            remark = parts[1].strip() if len(parts) > 1 else ""

            tool_data = tool_info.split()
            tool = tool_data[0]
            pocket = tool.split("T")[1]
            diameter_metric = float([x for x in tool_data if x.startswith("D")][0][1:])

        # Convert diameter to imperial
        # diameter_imperial = diameter_metric * 25.4
        diameter_imperial = diameter_metric
        diameter_imperial_str = "D+{:.6f}".format(diameter_imperial)

        # Clean the remark: strip leading semicolons and extra spaces
        remark = remark.lstrip(";").strip()

        # Add a semicolon and space if the remark exists, but only if it doesn't already start with one
        if remark and not remark.startswith(";"):
            remark = "; " + remark

        data[tool] = {
            "diameter": diameter_imperial_str,
            "remark": remark,
            "pocket": pocket,
        }

    return data


def update_master_file(master_data, updater_data):
    exceptions = ["T100"]  # Example tool numbers
    updated_data = {}

    for tool, updater_info in updater_data.items():
        if tool in exceptions:
            updated_data[tool] = master_data[tool]
            continue

        if tool in master_data:
            # Split the master data line and remove extra spaces
            master_parts = re.split(r"\s+", master_data[tool].strip())

            # Extract `Z` from the master data (preserve it)
            z_value = next((p for p in master_parts if p.startswith("Z+")), None)

            # If no `Z` found in master, use a default value
            if not z_value:
                z_value = "Z+0.000000"

            # Get D and U from the updater info (these are updated from the database)
            d_value = updater_info["diameter"].strip()
            u_value = updater_info.get("u_value", "U0")

            # Keep the remark from the updater, ensuring no double semicolons
            final_remark = updater_info["remark"]

            # Format the updated line correctly, ensuring proper spacing and integer U handling
            updated_data[tool] = (
                f"{master_parts[0]:<7}{master_parts[1]:<7}{z_value:<13}{d_value:<13}{u_value:<5} {final_remark}\n"
            )
        else:
            # Add a new tool if it's not in the master data, with correct spacing
            u_value = updater_info.get("u_value", "U0")
            new_entry = "{:<7}P{:<6}Z+0.000000   {:<13}{:<5} {}".format(
                tool,
                "0",
                updater_info["diameter"],
                u_value,
                updater_info["remark"],
            )
            updated_data[tool] = new_entry

    # Remove tools not in the updater file unless they are in the exceptions list
    for tool in list(master_data.keys()):  # Convert to list to avoid runtime error
        if tool not in updater_data and tool not in exceptions:
            del master_data[tool]

    # Append new tools to updated_data, ensuring exceptions are retained
    for tool, entry in master_data.items():
        if tool not in updated_data:
            updated_data[tool] = entry

    return updated_data


def write_master_file(file_path, header, data):
    with open(file_path, "w") as file:
        if header:
            file.write(
                header.strip() + "\n"
            )  # Ensure the header ends with a single newline
        sorted_entries = sorted(
            data.values(), key=lambda x: int(x.split()[0][1:])
        )  # Sort by numeric tool number
        for line in sorted_entries:
            file.write(
                line.strip() + "\n"
            )  # Ensure each line ends with a single newline


def main(update_data=None, master_file_path=None, updater_file_path=None):
    # Use config paths if not provided
    if master_file_path is None:
        master_file_path = config.get("file_paths", {}).get(
            "master_tool_table", "tool.tbl"
        )

    print(f"Merging tool tables...")
    print(f"  Master file: {master_file_path}")

    # Read the master file
    header, master_data = read_master_file(master_file_path)

    # Handle update data - either in-memory or from file
    if update_data is not None:
        print(f"  Using provided in-memory update data")
        # Convert list of lines to dictionary format expected by update_master_file
        updater_data = {}
        for line in update_data:
            if not line.strip():
                continue
            parts = line.split(";")
            tool_info = parts[0].strip()
            remark = parts[1].strip() if len(parts) > 1 else ""

            tool_data = tool_info.split()
            tool = tool_data[0]
            diameter_str = [x for x in tool_data if x.startswith("D")][0]
            diameter_value = float(diameter_str[1:])
            diameter_imperial_str = f"D+{diameter_value:.6f}"

            # Extract U value from the update data
            u_str = (
                [x for x in tool_data if x.startswith("U")][0]
                if any(x.startswith("U") for x in tool_data)
                else "U0"
            )

            if remark and not remark.startswith(";"):
                remark = "; " + remark

            updater_data[tool] = {
                "diameter": diameter_imperial_str,
                "remark": remark,
                "pocket": "0",
                "u_value": u_str,
            }
    else:
        if updater_file_path is None:
            updater_file_path = config.get("file_paths", {}).get(
                "tool_table", "update-tool.tbl"
            )
        print(f"  Update file: {updater_file_path}")
        updater_data = read_updater_file(updater_file_path)

    # Update the master data
    updated_master_data = update_master_file(master_data, updater_data)

    # Write the updated master data back to file
    write_master_file(master_file_path, header, updated_master_data)
    print(f"Master tool table updated: {master_file_path}")


if __name__ == "__main__":
    # Run with default config paths
    main()
