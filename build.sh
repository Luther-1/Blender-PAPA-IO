#!/bin/bash

# Configuration
PLUGIN_DIR="io_scene_papa"
OUTPUT_ZIP="Blender-PAPA-IO.zip"
FILES_TO_INCLUDE=("__init__.py" "import_papa.py" "export_papa.py" "papafile.py" "README.md" "LICENSE")

# Cleanup previous build artifacts
if [ -d "$PLUGIN_DIR" ]; then
    echo "Cleaning up previous temporary directory..."
    rm -rf "$PLUGIN_DIR"
fi

if [ -f "$OUTPUT_ZIP" ]; then
    echo "Removing old $OUTPUT_ZIP..."
    rm "$OUTPUT_ZIP"
fi

# Create directory structure
echo "Creating directory $PLUGIN_DIR..."
mkdir "$PLUGIN_DIR"

# Copy files
echo "Copying files..."
for file in "${FILES_TO_INCLUDE[@]}"; do
    if [ -f "$file" ]; then
        cp "$file" "$PLUGIN_DIR/"
    else
        echo "Warning: $file not found, skipping."
    fi
done

# Create Zip archive
echo "Zipping plugin..."
if command -v zip &> /dev/null; then
    zip -r "$OUTPUT_ZIP" "$PLUGIN_DIR"
elif command -v powershell.exe &> /dev/null; then
    echo "'zip' command not found, falling back to PowerShell..."
    powershell.exe -nologo -noprofile -command "Compress-Archive -Path '$PLUGIN_DIR' -DestinationPath '$OUTPUT_ZIP' -Force"
else
    echo "Error: Neither 'zip' nor 'powershell.exe' found. Cannot create archive."
    rm -rf "$PLUGIN_DIR"
    exit 1
fi

# Cleanup
echo "Cleaning up..."
rm -rf "$PLUGIN_DIR"

echo "Build complete! Archive created: $OUTPUT_ZIP"
