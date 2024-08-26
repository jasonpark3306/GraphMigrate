#!/bin/bash

# Check if a filename was provided
if [ $# -eq 0 ]; then
    echo "Please provide a filename as an argument."
    exit 1
fi

# Loop through all provided filenames
for file in "$@"
do
    # Check if the file exists
    if [ ! -f "$file" ]; then
        echo "File not found: $file"
        continue
    fi

    echo "Processing file: $file"

    # Create a temporary file
    temp_file=$(mktemp)

    # Use tr to remove carriage returns and output to temporary file
    tr -d '\r' < "$file" > "$temp_file"

    # Replace the original file with the modified one
    mv "$temp_file" "$file"

    echo "Completed processing: $file"
done

echo "All files processed."
