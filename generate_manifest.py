import os
import json
import sys


def list_files(directory, file_filter=None):
    return [
        f
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and (file_filter(f) if file_filter else True)
    ]


def main(source_dir, manifest_path):
    manifest = {}

    # Define source subdirs (relative to source_dir)
    source_subdirs = {
        "Tools/Bit": os.path.join(source_dir, "Tools", "Bit"),
        "Tools/Library": os.path.join(source_dir, "Tools", "Library"),
        "Tools/Shape": os.path.join(source_dir, "Tools", "Shape"),
        "PostProcessor": os.path.join(source_dir, "PostProcessor"),
        "Jobs": os.path.join(source_dir, "Jobs"),
    }

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
