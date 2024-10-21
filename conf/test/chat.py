import asyncio
import websockets
import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import base64
from PIL import Image, ImageTk
import io
import requests
import random
import string

class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("WebSocket Chat Client")

        self.websocket = None
        self.username = tk.StringVar(value=self.generate_random_username())
        self.message = tk.StringVar()
        self.base_url = tk.StringVar(value="http://58.233.69.198:8080/moment/images/")
        self.image_references = []  # List to keep references to all images

        # Chat display
        self.chat_display = scrolledtext.ScrolledText(master, height=20, width=50)
        self.chat_display.grid(row=0, column=0, columnspan=2, padx=5, pady=5)
        self.chat_display.tag_configure("bold", font=("Arial", 10, "bold"))

        # Message entry
        tk.Label(master, text="Message:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(master, textvariable=self.message, width=40).grid(row=1, column=1, padx=5, pady=5)

        # Button frame
        button_frame = tk.Frame(master)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)

        # Buttons
        tk.Button(button_frame, text="Send", command=self.send_message).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Send Image", command=self.send_image).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Set Base URL", command=self.set_base_url).pack(side=tk.LEFT, padx=5)

        # Connect automatically
        self.connect()

    def generate_random_username(self):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def connect(self):
        asyncio.create_task(self.websocket_connect())

    async def websocket_connect(self):
        try:
            self.websocket = await websockets.connect('ws://58.233.69.198:8765')
            self.chat_display.insert(tk.END, f"Connected to server as {self.username.get()}\n")
            asyncio.create_task(self.receive_messages())
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    async def receive_messages(self):
        try:
            while True:
                message = await self.websocket.recv()
                data = json.loads(message)
                if data.get('type') == 'base_url_updated':
                    self.base_url.set(data['content'])
                    self.chat_display.insert(tk.END, f"Base URL updated to: {data['content']}\n")
                else:
                    sender = data.get('sender', 'Unknown')
                    content = data.get('content', '')
                    is_image = data.get('is_image', False)
                    self.chat_display.insert(tk.END, f"{sender}: ", "bold")
                    if is_image:
                        self.display_image(content)
                    else:
                        self.chat_display.insert(tk.END, f"{content}\n")
                self.chat_display.see(tk.END)
        except websockets.exceptions.ConnectionClosed:
            self.chat_display.insert(tk.END, "Disconnected from server\n")

    def display_image(self, image_url):
        try:
            if image_url.startswith(self.base_url.get()):
                full_url = image_url
            else:
                full_url = f"{self.base_url.get()}{image_url}"
            
            response = requests.get(full_url)
            response.raise_for_status()
            
            image_data = response.content
            
            image = Image.open(io.BytesIO(image_data))
            image.thumbnail((200, 200))  # Resize image to fit in chat
            photo = ImageTk.PhotoImage(image)
            self.chat_display.image_create(tk.END, image=photo)
            self.chat_display.insert(tk.END, "\n")
            
            # Keep a reference to avoid garbage collection
            self.image_references.append(photo)
        except requests.RequestException as e:
            self.chat_display.insert(tk.END, f"[Error fetching image]\n")
        except IOError as e:
            self.chat_display.insert(tk.END, f"[Error processing image]\n")
        except Exception as e:
            self.chat_display.insert(tk.END, f"[Error displaying image]\n")

            
    def send_message(self):
        if self.websocket:
            message = {
                'sender': self.username.get(),
                'content': self.message.get(),
                'type': 'text'
            }
            asyncio.create_task(self.websocket.send(json.dumps(message)))
            self.message.set("")
        else:
            messagebox.showerror("Error", "Not connected to server")

    def send_image(self):
        if self.websocket:
            file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif")])
            if file_path:
                with open(file_path, "rb") as image_file:
                    file_data = image_file.read()
                    file_size = len(file_data)
                    chunk_size = 64 * 1024  # 64 KB chunks
                    
                    # Send file info
                    info_message = {
                        'sender': self.username.get(),
                        'type': 'image_info',
                        'file_size': file_size,
                        'chunk_size': chunk_size
                    }
                    asyncio.create_task(self.websocket.send(json.dumps(info_message)))
                    
                    # Send file data in chunks
                    for i in range(0, file_size, chunk_size):
                        chunk = file_data[i:i+chunk_size]
                        chunk_message = {
                            'sender': self.username.get(),
                            'type': 'image_chunk',
                            'chunk': base64.b64encode(chunk).decode('utf-8'),
                            'sequence': i // chunk_size
                        }
                        asyncio.create_task(self.websocket.send(json.dumps(chunk_message)))
                    
                    # Send completion message
                    complete_message = {
                        'sender': self.username.get(),
                        'type': 'image_complete'
                    }
                    asyncio.create_task(self.websocket.send(json.dumps(complete_message)))
        else:
            messagebox.showerror("Error", "Not connected to server")

    def set_base_url(self):
        if self.websocket:
            new_base_url = self.base_url.get()
            if not new_base_url.endswith('/'):
                new_base_url += '/'
            message = {
                'type': 'set_base_url',
                'content': new_base_url
            }
            self.base_url.set(new_base_url)  # Update the StringVar
            asyncio.create_task(self.websocket.send(json.dumps(message)))
        else:
            messagebox.showerror("Error", "Not connected to server")

async def main():
    root = tk.Tk()
    client = ChatClient(root)
    while True:
        root.update()
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())