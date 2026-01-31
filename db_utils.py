from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import text, select
from settings import load_config
from datetime import datetime
import uuid
from auth_utils import generate_hmac
from settings import CONFIG  # For configuration settings
import requests
import re
from urllib.parse import urlencode

# Define SQLAlchemy Base and Tool Model
Base = declarative_base()


class Tool(Base):
    __tablename__ = "tools"

    ToolNumber = Column(Integer, primary_key=True, autoincrement=True)
    ToolName = Column(Text)
    ToolType = Column(Text)
    Shape = Column(Text)
    ToolShankSize = Column(Text)
    Flutes = Column(Text)
    OAL = Column(Text)
    LOC = Column(Text)
    ToolMaxRPM = Column(Integer)
    ToolDiameter = Column(Text)
    Stickout = Column(Text)
    ToolMaterial = Column(Text)
    ToolCoating = Column(Text)
    PartNumber = Column(Text)
    ManufacturerName = Column(Text)
    ToolOrderURL = Column(Text)
    Materials = Column(Text)
    SuggestedRPM = Column(Text)
    SuggestedMaxDOC = Column(Text)
    AdditionalNotes = Column(Text)
    SuggestedFeedRate = Column(Text)
    ToolImageFileName = Column(Text)
    ImageHash = Column(Text)
    ShapeParameter = Column(Text)
    ShapeAttribute = Column(Text)
    Units = Column(Text)  # Imperial or Metric - for FreeCAD v1.2+


class ToolModel(Base):
    __tablename__ = "tool"

    tool_no = Column(Integer, primary_key=True, nullable=False)
    diameter = Column(Float, nullable=True)
    remark = Column(String, nullable=True)
    tool_table_id = Column(Integer, ForeignKey("tool_table.id"), nullable=True)

    # Relationship with ToolTable
    tool_table = relationship("ToolTable", back_populates="tools")

    def __repr__(self):
        return f"<ToolModel(tool_no={self.tool_no}, diameter={self.diameter}, remark={self.remark}, tool_table_id={self.tool_table_id})>"


class ToolPropertiesModel(Base):
    __tablename__ = "tool_properties"

    tool_no = Column(Integer, primary_key=True, nullable=False)
    max_rpm = Column(Float, nullable=True)
    tool_table_id = Column(Integer, ForeignKey("tool_table.id"), nullable=True)

    # Relationship with ToolTable
    tool_table = relationship("ToolTable", back_populates="tool_properties")

    def __repr__(self):
        return f"<ToolPropertiesModel(tool_no={self.tool_no}, max_rpm={self.max_rpm})>"


class ToolTable(Base):
    __tablename__ = "tool_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)

    # Relationships with Tool and ToolProperties
    tools = relationship(
        "ToolModel", back_populates="tool_table", cascade="all, delete-orphan"
    )
    tool_properties = relationship(
        "ToolPropertiesModel", back_populates="tool_table", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ToolTable(id={self.id}, name={self.name})>"


# Dynamically construct the database URL
def get_database_url():
    db_type = CONFIG.get("database", {}).get("type", "sqlite").lower()

    if db_type == "sqlite":
        # Use SQLite database path
        return f"sqlite:///{CONFIG['file_paths']['database_path']}"
    elif db_type in {"mysql", "postgresql"}:
        # Use MySQL or PostgreSQL credentials
        username = CONFIG["database"].get("username", "")
        password = CONFIG["database"].get("password", "")
        host = CONFIG["database"].get("host", "localhost")
        database = CONFIG["database"].get("database", "tools")
        return f"{db_type}://{username}:{password}@{host}/{database}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


# Initialize the database engine and session
DATABASE_URL = get_database_url()
HMAC_ENABLED = CONFIG.get("api", {}).get("hmac_enabled", False)
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


def set_db_mode(mode, api_url=None):
    """
    Set the database mode dynamically, falling back to API if SQL connection fails.

    :param mode: 'direct' or 'api'
    :param api_url: Base URL for API requests (if mode is 'api')
    """
    global DB_MODE, API_URL
    DB_MODE = mode
    API_URL = api_url

    if mode == "direct":
        # Test SQL connection
        try:
            # Ensure tables are created
            Base.metadata.create_all(engine)
            with Session() as session:
                session.execute("SELECT 1")  # Simple query to test the connection
                print("[INFO] Database connection successful.")
        except Exception as e:
            print(f"[ERROR] SQL connection failed: {str(e)}. Falling back to API mode.")
            DB_MODE = "api"
            if not api_url:
                raise RuntimeError(
                    "API URL must be provided when falling back to API mode."
                )


def make_api_request(method, endpoint, data=None):
    """
    Helper function to make API requests with optional HMAC signing.

    Args:
        method (str): HTTP method (GET, POST, PUT, DELETE).
        endpoint (str): API endpoint path (e.g., '/tools').
        data (dict, optional): Payload for POST/PUT requests or query parameters for GET.

    Returns:
        dict: The response from the API as a JSON object.
    """
    if DB_MODE != "api" or not API_URL:
        raise RuntimeError("API mode is not configured properly.")

    # Construct the full URL
    url = f"{API_URL}{endpoint}"  # Full URL including path
    headers = {"Content-Type": "application/json"}
    signed_data = data.copy() if data else {}

    if HMAC_ENABLED:
        # Add HMAC-related fields
        signed_data["timestamp"] = datetime.utcnow().isoformat()
        signed_data["nonce"] = str(uuid.uuid4())

        # Serialize query parameters into the URL for HMAC generation
        query_string = urlencode(signed_data)
        separator = "&" if "?" in url else "?"
        full_url = f"{url}{separator}{query_string}"

        # Generate the signature
        signed_data["signature"] = generate_hmac(full_url)

    try:
        if method == "GET":
            # Send data as query parameters
            response = requests.get(url, params=signed_data, headers=headers)
        elif method in ("POST", "PUT", "DELETE"):
            # Send data as JSON payload
            response = requests.request(method, url, json=signed_data, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API request failed: {e}")


def fetch_column_names(table_name):
    """
    Fetch column names from the specified table in the database or via API.

    Args:
        table_name (str): The name of the table.

    Returns:
        List[str]: A list of column names.
    """
    if DB_MODE == "api":
        # Use the API to fetch column names and extract the list
        response = make_api_request("GET", f"/column_names/{table_name}")
        return response.get("column_names", [])  # Extract the list of column names

    with Session() as session:
        # Detect the database backend
        backend = session.bind.dialect.name

        if backend == "sqlite":
            # SQLite query
            result = session.execute(
                text(f"PRAGMA table_info({table_name});")
            ).fetchall()
            return [row["name"] for row in result]

        elif backend in ("mysql", "mariadb"):
            # MariaDB/MySQL query
            schema_name = session.bind.url.database
            result = session.execute(
                text(
                    """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :schema_name AND TABLE_NAME = :table_name
            """
                ),
                {"schema_name": schema_name, "table_name": table_name},
            ).fetchall()
            return [row[0] for row in result]

        else:
            raise ValueError(f"Unsupported database backend: {backend}")


def fetch_tool_data(tool_number=None):
    """
    Fetch tool data from the database or via API.
    Args:
        tool_number (str, optional): The tool number to fetch. If None, fetches all tools.
    Returns:
        tuple: A tuple containing:
            - List[dict]: Tool data rows as a list of dictionaries.
            - List[str]: Column names corresponding to the data.
    """
    if DB_MODE == "api":
        endpoint = f"/tool_data"
        if tool_number:
            endpoint += f"?tool_number={tool_number}"
        response = make_api_request("GET", endpoint)

        # Ensure response includes both 'tools' and 'columns'
        if (
            not isinstance(response, dict)
            or "tools" not in response
            or "columns" not in response
        ):
            raise ValueError("Invalid API response format for tool data.")

        return response["tools"], response["columns"]

    with Session() as session:
        query = select(Tool)
        if tool_number is not None:
            query = query.filter(Tool.ToolNumber == tool_number)

        # Execute the query and fetch results
        tools = session.execute(query).scalars().all()
        columns = Tool.__table__.columns.keys()

        # Convert ORM objects to dictionaries and remove internal attributes
        rows_as_dicts = []
        for tool in tools:
            tool_dict = {key: getattr(tool, key) for key in columns}
            rows_as_dicts.append(tool_dict)

        return rows_as_dicts, list(columns)


def fetch_filtered(keyword):
    """
    Fetch tools filtered by a keyword from the database or via API.

    Args:
        keyword (str): The keyword to filter tools by.

    Returns:
        tuple: A tuple containing:
            - List[dict]: Filtered tool data rows as dictionaries.
            - List[str]: Column names corresponding to the data.
    """
    if DB_MODE == "api":
        response = make_api_request("GET", f"/filtered", data={"keyword": keyword})

        # Ensure response includes both 'tools' and 'columns'
        if (
            not isinstance(response, dict)
            or "tools" not in response
            or "columns" not in response
        ):
            raise ValueError("Invalid API response format for tool data.")

        return response["tools"], response["columns"]

    keyword = f"%{keyword}%"
    with Session() as session:
        # Query the database for matching tools
        query = select(Tool).filter(
            Tool.ToolName.like(keyword)
            | Tool.ToolType.like(keyword)
            | Tool.ManufacturerName.like(keyword)
        )
        tools = session.execute(query).scalars().all()

        # Extract column names dynamically
        columns = Tool.__table__.columns.keys()

        # Convert each SQLAlchemy row object into a dictionary
        rows_as_dicts = [tool.__dict__ for tool in tools]

        # Remove SQLAlchemy's internal state key ("_sa_instance_state")
        for row in rows_as_dicts:
            row.pop("_sa_instance_state", None)

        return rows_as_dicts, columns


def fetch_tool_numbers_and_details():
    """
    Fetch all tool numbers and names from the database or via API for generating file paths or other uses.

    Returns:
        List[dict]: A list of dictionaries, each containing `ToolNumber` and `ToolName`.
    """
    if DB_MODE == "api":
        response = make_api_request("GET", "/tool_numbers_and_details")
        return response["tool_numbers_and_details"]

    with Session() as session:
        query = select(Tool.ToolNumber, Tool.ToolName).order_by(Tool.ToolNumber)
        tools = session.execute(query).all()
        return [{"ToolNumber": tool[0], "ToolName": tool[1]} for tool in tools]


class ShapeData:
    """
    Wrapper class to emulate attribute access for shape data.
    """

    def __init__(self, shape_name, shape_parameter, shape_attribute):
        self.ShapeName = shape_name
        self.ShapeParameter = shape_parameter
        self.ShapeAttribute = shape_attribute


def fetch_shapes(shape_name=None):
    if DB_MODE == "api":
        endpoint = f"/shapes"
        if shape_name:
            endpoint += f"?shape_name={shape_name}"
        response = make_api_request("GET", endpoint)

        if shape_name:
            # Convert the API response into an object-like structure to mimic SQLAlchemy row behavior
            shape_data = response["shapes"]
            return type("ShapeRow", (object,), shape_data)()
        else:
            result = response["shapes"]
            return result

    # SQL mode remains unchanged
    try:
        with Session() as session:
            if shape_name:
                # Fetch the specific shape's row
                result = session.execute(
                    text("SELECT * FROM FCShapes WHERE ShapeName = :shape_name"),
                    {"shape_name": shape_name},
                ).fetchone()
                return result  # Return the row as-is
            else:
                # Fetch all shape names
                shapes = session.execute(
                    text("SELECT ShapeName FROM FCShapes ORDER BY ShapeName")
                ).fetchall()
                return [row[0] for row in shapes]  # Extract just the ShapeName column
    except Exception as e:
        print(f"Error fetching shapes: {e}")
        return None if shape_name else []


def fetch_unique_column_values(column_name):
    """
    Fetch unique values for a given column from the tools table, or via API.

    Args:
        column_name (str): The name of the column.

    Returns:
        List: A list of unique values.
    """
    if DB_MODE == "api":
        # Ensure API response matches SQL mode output
        response = make_api_request("GET", f"/unique_column_values/tools/{column_name}")
        return list(response["unique_values"])

    with Session() as session:
        query = text(
            f"SELECT DISTINCT {column_name} FROM tools WHERE {column_name} IS NOT NULL"
        )
        result = session.execute(query).fetchall()
        return [row[0] for row in result]


def fetch_image_hash(tool_number):
    """
    Fetch the stored image hash for a specific tool, or via API.

    Args:
        tool_number (int): The tool number.

    Returns:
        str: The stored image hash, or None if not found.
    """
    if DB_MODE == "api":
        response = make_api_request("GET", f"/image_hash/{tool_number}")
        return response["image_hash"]

    with Session() as session:
        tool = session.query(Tool).filter_by(ToolNumber=tool_number).first()
        return tool.ImageHash if tool else None


def insert(tool_data):
    """
    Insert a new tool into the database and update tool and tool_properties tables, or via API.

    Args:
        tool_data (dict): Dictionary of tool data to insert.
    """
    if DB_MODE == "api":
        return make_api_request("POST", "/insert/tool", data=tool_data)

    with Session() as session:
        # Exclude ImageHash
        filtered_tool_data = {
            key: value for key, value in tool_data.items() if key != "ImageHash"
        }

        # Preprocess ToolMaxRPM for Tool (as INT)
        tool_max_rpm_int = int(
            extract_numeric(tool_data.get("ToolMaxRPM"), field_type="rpm") or 0
        )
        filtered_tool_data[
            "ToolMaxRPM"
        ] = tool_max_rpm_int  # Add processed integer value for ToolMaxRPM

        # Insert into the main Tool table
        tool = Tool(**filtered_tool_data)
        session.add(tool)

        # Convert ToolDiameter to numeric (imperial if necessary)
        diameter = extract_numeric(
            tool_data.get("ToolDiameter"), field_type="dimension"
        )

        # Insert into the `tool` table
        tool_record = ToolModel(
            tool_no=tool_data["ToolNumber"],
            diameter=diameter,
            remark=tool_data["ToolName"],
            tool_table_id=1,  # Always use tool_table_id = 1
        )
        session.add(tool_record)

        # Preprocess ToolMaxRPM for tool_properties (as FLOAT)
        tool_max_rpm_float = float(tool_max_rpm_int)

        # Insert into the `tool_properties` table
        tool_properties_record = ToolPropertiesModel(
            tool_no=tool_data["ToolNumber"],
            max_rpm=tool_max_rpm_float,  # Use float value for ToolMaxRPM
            tool_table_id=1,  # Always use tool_table_id = 1
        )
        session.add(tool_properties_record)

        session.commit()


def update(tool_number, updated_data):
    """
    Update an existing tool in the database, excluding certain fields, or via API.

    Args:
        tool_number (int): ToolNumber of the tool to update.
        updated_data (dict): Dictionary of updated data.
    """
    if DB_MODE == "api":
        return make_api_request("PUT", f"/update/tool/{tool_number}", data=updated_data)

    excluded_fields = {"ImageHash"}  # Fields to exclude from updates

    with Session() as session:
        # Update the main Tool table
        query = select(Tool).filter_by(ToolNumber=tool_number)
        tool = session.execute(query).scalars().first()
        if tool:
            tool_max_rpm_int = int(
                extract_numeric(updated_data.get("ToolMaxRPM"), field_type="rpm") or 0
            )
            updated_tool_data = {
                key: value
                for key, value in updated_data.items()
                if key not in excluded_fields
            }
            updated_tool_data["ToolMaxRPM"] = tool_max_rpm_int

            for key, value in updated_tool_data.items():
                setattr(tool, key, value)
            session.commit()
            print(
                f"Tool {tool_number} updated successfully, excluding fields: {excluded_fields}."
            )
        else:
            print(f"Tool {tool_number} not found.")

        # Update the `tool` table
        tool_record = (
            session.execute(select(ToolModel).filter_by(tool_no=tool_number))
            .scalars()
            .first()
        )
        if tool_record:
            if "ToolDiameter" in updated_data:
                diameter = extract_numeric(
                    updated_data["ToolDiameter"], field_type="dimension"
                )
                if diameter is not None:
                    tool_record.diameter = diameter
            if "ToolName" in updated_data:
                tool_record.remark = updated_data["ToolName"]
            session.commit()

        # Update the `tool_properties` table
        tool_properties_record = (
            session.execute(select(ToolPropertiesModel).filter_by(tool_no=tool_number))
            .scalars()
            .first()
        )
        if tool_properties_record:
            if "ToolMaxRPM" in updated_data:
                tool_max_rpm_float = float(
                    extract_numeric(updated_data.get("ToolMaxRPM"), field_type="rpm")
                    or 0
                )
                tool_properties_record.max_rpm = tool_max_rpm_float
            session.commit()


def update_image_hash(tool_number, image_hash):
    """
    Update the image hash for a specific tool in the database or via API.

    Args:
        tool_number (int): The tool number whose image hash is being updated.
        image_hash (str): The new SHA-256 hash of the tool's image.

    Returns:
        None
    """
    if DB_MODE == "api":
        return make_api_request(
            "PUT", f"/update_image_hash/{tool_number}", data={"image_hash": image_hash}
        )

    with Session() as session:
        query = select(Tool).filter_by(ToolNumber=tool_number)
        tool = session.execute(query).scalars().first()
        if tool:
            tool.ImageHash = image_hash
            session.commit()


def delete(tool_number):
    """
    Delete a tool from the database or via API.

    Args:
        tool_number (int): ToolNumber of the tool to delete.
    """
    if DB_MODE == "api":
        return make_api_request("DELETE", f"/delete/tool/{tool_number}")

    with Session() as session:
        # Delete from the main Tool table
        tool = (
            session.execute(select(Tool).filter_by(ToolNumber=tool_number))
            .scalars()
            .first()
        )
        if tool:
            session.delete(tool)

        # Delete from the `tool_properties` table
        tool_properties_record = (
            session.execute(select(ToolPropertiesModel).filter_by(tool_no=tool_number))
            .scalars()
            .first()
        )
        if tool_properties_record:
            session.delete(tool_properties_record)

        # Delete from the `tool` table
        tool_record = (
            session.execute(select(ToolModel).filter_by(tool_no=tool_number))
            .scalars()
            .first()
        )
        if tool_record:
            session.delete(tool_record)

        # Commit all changes in a single transaction
        session.commit()


def extract_numeric(value, field_type=None):
    """
    Extract the numeric portion from a string containing text and numbers and handle unit conversion.

    Args:
        value (str): The input string, e.g., '12.34 mm' or '1.5 in'.
        field_type (str, optional): The type of the field (e.g., 'dimension', 'rpm').
                                    Determines if unit conversion is applied.

    Returns:
        float: The numeric value, converted if necessary (e.g., to imperial for dimensions),
               or None if no numeric portion is found.
    """
    if not value:
        return None

    value = value.replace(",", "")

    # Extract the numeric portion
    match = re.search(r"-?[0-9.]+", value)
    if not match:
        return None

    number = float(match.group())

    # Check for units if field_type is 'dimension'
    if field_type == "dimension":
        # Convert to lowercase for unit matching
        value = value.lower()

        # If the value is in mm, convert to inches
        if "mm" in value:
            number /= 25.4  # Convert millimeters to inches
        elif '"' in value or "in" in value:
            pass  # Already in inches; no conversion needed

    return number
