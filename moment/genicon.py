import os
from PIL import Image

def remove_background(input_path, output_path):
    with Image.open(input_path) as img:
        img = img.convert("RGBA")
        
        # Get the data
        datas = img.getdata()
        
        newData = []
        for item in datas:
            # If the pixel is white (255, 255, 255) or very close to white, make it transparent
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                newData.append((255, 255, 255, 0))
            else:
                newData.append(item)
        
        img.putdata(newData)
        img.save(output_path, "PNG")
        print(f"Processed and saved {os.path.basename(output_path)}")

def process_images(src_folder, target_folder):
    # Create target folder if it doesn't exist
    os.makedirs(target_folder, exist_ok=True)
    
    # Process all image files in the src folder
    for filename in os.listdir(src_folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            input_path = os.path.join(src_folder, filename)
            output_filename = f"ht_{filename.split('.')[0]}.png"
            output_path = os.path.join(target_folder, output_filename)
            
            remove_background(input_path, output_path)

# Set your input and output directories
src_folder = "."  # Source folder containing original images
target_folder = "target"  # Target folder for processed images

# Process all images
if os.path.exists(src_folder):
    process_images(src_folder, target_folder)
    print("\nImage processing completed.")
else:
    print(f"Source folder '{src_folder}' not found. Please create it and add your images.")