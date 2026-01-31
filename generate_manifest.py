import os
import json
import sys
import yaml


def load_config(config_file="config.yaml"):
    """Load configuration to get FreeCAD versions."""
    if not os.path.exists(config_file):
        return None
    with open(config_file, "r") as file:
        return yaml.safe_load(file)


def list_files(directory, file_filter=None):
    return [
        f
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and (file_filter(f) if file_filter else True)
    ]


def main(source_dir, manifest_path):
    manifest = {}

    # Load config to get versions dynamically
    config = load_config()
    versions = (
        config.get("freecad", {}).get("versions", ["v1-0"]) if config else ["v1-0"]
    )

    # Start with base paths structure
    source_subdirs = {}

    # Add paths for each configured version
    for version in versions:
        if version == "v1-0":
            # v1.0 uses Tools/Bit/ structure
            source_subdirs["Tools/Bit"] = os.path.join(source_dir, "Tools", "Bit")
            source_subdirs["Tools/Library"] = os.path.join(
                source_dir, "Tools", "Library"
            )
            source_subdirs["Tools/Shape"] = os.path.join(source_dir, "Tools", "Shape")
        else:
            # v1.1+ uses CAMAssets/v1-x/Tools/Bit/ structure
            source_subdirs[f"CAMAssets/{version}/Tools/Bit"] = os.path.join(
                source_dir, "CAMAssets", version, "Tools", "Bit"
            )
            source_subdirs[f"CAMAssets/{version}/Tools/Library"] = os.path.join(
                source_dir, "CAMAssets", version, "Tools", "Library"
            )

    # Add common paths
    source_subdirs["PostProcessor"] = os.path.join(source_dir, "PostProcessor")
    source_subdirs["Jobs"] = os.path.join(source_dir, "Jobs")

    # Scan each subdir
    for group, path in source_subdirs.items():
        if os.path.isdir(path):
            manifest[group] = list_files(path)
        else:
            manifest[group] = []

    # Write manifest
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_manifest.py <source_dir> <manifest_path>")
        sys.exit(1)
    source_dir = sys.argv[1]
    manifest_path = sys.argv[2]
    if not os.path.isdir(source_dir):
        print(f"Error: {source_dir} is not a directory.")
        sys.exit(1)
    main(source_dir, manifest_path)
