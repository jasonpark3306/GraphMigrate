from PIL import Image, ImageDraw, ImageFont
import os

def create_gradient(size, color1, color2):
    base = Image.new('RGB', size, color1)
    top = Image.new('RGB', size, color2)
    mask = Image.new('L', size)
    mask_data = []
    for y in range(size[1]):
        mask_data.extend([int(255 * (y / size[1]))] * size[0])
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def create_icon(name, draw_function, size=(200, 200)):
    # Create gradient background
    top_color = (82, 153, 211)  # Darker blue
    bottom_color = (115, 176, 228)  # Lighter blue
    background = create_gradient(size, top_color, bottom_color)
    image = background.convert('RGBA')
    draw = ImageDraw.Draw(image)
    
    # Draw the icon
    draw_function(draw, size)
    
    # Add text with larger, bold font
    try:
        font = ImageFont.truetype("arialbd.ttf", 18)  # Arial Bold, larger size
    except IOError:
        font = ImageFont.load_default().font_variant(size=18)  # Fallback to default font if Arial Bold is not available
    
    # Split text into multiple lines if it's too long
    words = name.split()
    lines = []
    current_line = words[0]
    for word in words[1:]:
        if draw.textlength(current_line + " " + word, font=font) < size[0] - 20:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    
    # Calculate total text height
    line_height = font.size + 2
    total_text_height = len(lines) * line_height
    
    # Draw each line of text
    y_text = size[1] - total_text_height - 10
    for line in lines:
        text_width = draw.textlength(line, font=font)
        x_text = (size[0] - text_width) / 2
        draw.text((x_text, y_text), line, fill=(255, 255, 255), font=font)
        y_text += line_height
    
    return image

# ... (rest of the code remains the same)

def retail_ecommerce(draw, size):
    draw.rectangle([50, 50, 150, 110], outline="white", width=2)
    draw.line([50, 80, 150, 80], fill="white", width=2)
    draw.ellipse([60, 120, 90, 150], outline="white", width=2)
    draw.ellipse([110, 120, 140, 150], outline="white", width=2)

def travel_hospitality(draw, size):
    draw.line([100, 50, 50, 150], fill="white", width=2)
    draw.line([100, 50, 150, 150], fill="white", width=2)
    draw.line([75, 100, 125, 100], fill="white", width=2)

def financial_services(draw, size):
    draw.rectangle([70, 70, 130, 150], outline="white", width=2)
    draw.line([70, 70, 100, 50], fill="white", width=2)
    draw.line([100, 50, 130, 70], fill="white", width=2)

def tech_business_services(draw, size):
    draw.arc([50, 50, 150, 150], 0, 360, fill="white", width=2)
    draw.line([75, 75, 125, 125], fill="white", width=2)
    draw.line([75, 125, 125, 75], fill="white", width=2)

def telecom(draw, size):
    draw.rectangle([70, 50, 130, 150], outline="white", width=2)
    draw.ellipse([90, 70, 110, 90], outline="white", width=2)
    draw.line([85, 130, 115, 130], fill="white", width=2)

def media_entertainment(draw, size):
    draw.rectangle([60, 60, 140, 140], outline="white", width=2)
    draw.polygon([(85, 75), (85, 125), (135, 100)], fill="white")

def gaming(draw, size):
    draw.rectangle([50, 50, 150, 150], outline="white", width=2)
    font = ImageFont.truetype("arial.ttf", 36)
    draw.text((70, 80), "777", fill="white", font=font)
    draw.ellipse([90, 120, 110, 140], outline="white", width=2)

def manufacturing_utilities(draw, size):
    draw.arc([50, 50, 150, 150], 0, 360, fill="white", width=2)
    draw.line([75, 75, 125, 125], fill="white", width=2)
    draw.line([75, 125, 125, 75], fill="white", width=2)
    draw.rectangle([90, 90, 110, 110], outline="white", width=2)

icons = [
    ("Retail & E-Commerce", retail_ecommerce),
    ("Travel & Hospitality", travel_hospitality),
    ("Financial Services", financial_services),
    ("Technology & Business Services", tech_business_services),
    ("Telecom", telecom),
    ("Media & Entertainment", media_entertainment),
    ("Gaming", gaming),
    ("Manufacturing & Utilities", manufacturing_utilities)
]

# Create 'icons' directory if it doesn't exist
if not os.path.exists('icons'):
    os.makedirs('icons')

# Create and save each icon
for name, draw_func in icons:
    icon = create_icon(name, draw_func)
    icon.save(f"icons/{name.replace(' & ', '_').replace(' ', '_').lower()}.png")

print("Icons created and saved in the 'icons' directory.")