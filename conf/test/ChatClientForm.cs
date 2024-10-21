using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Linq;

namespace GraphMigrate
{
    public partial class ChatClientForm : Form
    {
        private ClientWebSocket webSocket;
        private System.ComponentModel.IContainer components = null;
        private string username;
        private string baseUrl = "http://58.233.69.198:8080/moment/images/";
        private List<Image> imageReferences = new List<Image>();
        public ChatClientForm()
        {
            InitializeComponent();
            sendButton.Click += sendButton_Click;
            sendImageButton.Click += sendImageButton_Click;
            setBaseUrlButton.Click += setBaseUrlButton_Click;
            username = GenerateRandomUsername();
            Connect();
        }


        private string GenerateRandomUsername()
        {
            const string chars = "abcdefghijklmnopqrstuvwxyz0123456789";
            var random = new Random();
            return new string(Enumerable.Repeat(chars, 8)
                .Select(s => s[random.Next(s.Length)]).ToArray());
        }

        private async void Connect()
        {
            try
            {
                webSocket = new ClientWebSocket();
                await webSocket.ConnectAsync(new Uri("ws://58.233.69.198:8765"), CancellationToken.None);
                chatDisplay.AppendText($"Connected to server as {username}\n");
                _ = ReceiveMessages();
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Connection Error: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private async Task ReceiveMessages()
        {
            var buffer = new byte[4096];
            try
            {
                while (webSocket.State == WebSocketState.Open)
                {
                    var result = await webSocket.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        var message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        var data = JObject.Parse(message);
                        if (data["type"]?.ToString() == "base_url_updated")
                        {
                            baseUrl = data["content"].ToString();
                            Invoke((MethodInvoker)delegate
                            {
                                chatDisplay.AppendText($"Base URL updated to: {baseUrl}\n");
                            });
                        }
                        else
                        {
                            var sender = data["sender"]?.ToString() ?? "Unknown";
                            var content = data["content"]?.ToString() ?? "";
                            var isImage = data["is_image"]?.ToObject<bool>() ?? false;
                            Invoke((MethodInvoker)delegate
                            {
                                chatDisplay.SelectionFont = new Font(chatDisplay.Font, FontStyle.Bold);
                                chatDisplay.AppendText($"{sender}: ");
                                chatDisplay.SelectionFont = new Font(chatDisplay.Font, FontStyle.Regular);
                                if (isImage)
                                {
                                    DisplayImage(content);
                                }
                                else
                                {
                                    chatDisplay.AppendText($"{content}\n");
                                }
                                chatDisplay.ScrollToCaret();
                            });
                        }
                    }
                }
            }
            catch (WebSocketException)
            {
                Invoke((MethodInvoker)delegate
                {
                    chatDisplay.AppendText("Disconnected from server\n");
                });
            }
        }



        private async void DisplayImage(string imageUrl)
        {
            try
            {
                var fullUrl = imageUrl.StartsWith(baseUrl) ? imageUrl : $"{baseUrl}{imageUrl}";
                using (var httpClient = new HttpClient())
                {
                    var imageData = await httpClient.GetByteArrayAsync(fullUrl);
                    using (var ms = new MemoryStream(imageData))
                    {
                        var image = Image.FromStream(ms);
                        var thumbnail = image.GetThumbnailImage(200, 200, null, IntPtr.Zero);
                        Clipboard.SetImage(thumbnail);
                        chatDisplay.Paste();
                        chatDisplay.AppendText("\n");
                        imageReferences.Add(thumbnail);
                    }
                }
            }
            catch (Exception)
            {
                chatDisplay.AppendText("[Error displaying image]\n");
            }
        }

        private async void SendMessage()
        {
            if (webSocket?.State == WebSocketState.Open)
            {
                var message = new
                {
                    sender = username,
                    content = messageTextBox.Text,
                    type = "text"
                };
                var json = JsonConvert.SerializeObject(message);
                var buffer = Encoding.UTF8.GetBytes(json);
                await webSocket.SendAsync(new ArraySegment<byte>(buffer), WebSocketMessageType.Text, true, CancellationToken.None);
                messageTextBox.Clear();
            }
            else
            {
                MessageBox.Show("Not connected to server", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }


        private async void SendImage()
        {
            Console.WriteLine("SendImage method started");
            try
            {
                if (webSocket?.State == WebSocketState.Open)
                {
                    Console.WriteLine("WebSocket is open");
                    using (var openFileDialog = new OpenFileDialog())
                    {
                        openFileDialog.Filter = "Image files (*.png;*.jpg;*.jpeg;*.gif)|*.png;*.jpg;*.jpeg;*.gif";
                        if (openFileDialog.ShowDialog() == DialogResult.OK)
                        {
                            Console.WriteLine($"File selected: {openFileDialog.FileName}");
                            var fileData = await File.ReadAllBytesAsync(openFileDialog.FileName);
                            Console.WriteLine($"File size: {fileData.Length} bytes");
                            
                            // 파일 전송 로직...
                            await SendFileInChunks(fileData);

                            Console.WriteLine("File sending completed");
                        }
                        else
                        {
                            Console.WriteLine("File selection cancelled");
                        }
                    }
                }
                else
                {
                    Console.WriteLine("WebSocket is not open");
                    MessageBox.Show("Not connected to server", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error in SendImage: {ex.Message}");
                MessageBox.Show($"Error sending image: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private async Task SendFileInChunks(byte[] fileData)
        {
            var fileSize = fileData.Length;
            const int chunkSize = 64 * 1024; // 64 KB chunks

            // Send file info
            var infoMessage = new
            {
                sender = username,
                type = "image_info",
                file_size = fileSize,
                chunk_size = chunkSize
            };
            await SendJsonMessage(infoMessage);

            // Send file data in chunks
            for (int i = 0; i < fileSize; i += chunkSize)
            {
                var chunk = new byte[Math.Min(chunkSize, fileSize - i)];
                Array.Copy(fileData, i, chunk, 0, chunk.Length);
                var chunkMessage = new
                {
                    sender = username,
                    type = "image_chunk",
                    chunk = Convert.ToBase64String(chunk),
                    sequence = i / chunkSize
                };
                await SendJsonMessage(chunkMessage);
            }

            // Send completion message
            var completeMessage = new
            {
                sender = username,
                type = "image_complete"
            };
            await SendJsonMessage(completeMessage);
        }


        private async Task SendJsonMessage(object message)
        {
            var json = JsonConvert.SerializeObject(message);
            var buffer = Encoding.UTF8.GetBytes(json);
            await webSocket.SendAsync(new ArraySegment<byte>(buffer), WebSocketMessageType.Text, true, CancellationToken.None);
        }

        private async void SetBaseUrl()
        {
            if (webSocket?.State == WebSocketState.Open)
            {
                var newBaseUrl = baseUrlTextBox.Text;
                if (!newBaseUrl.EndsWith("/"))
                {
                    newBaseUrl += "/";
                }
                var message = new
                {
                    type = "set_base_url",
                    content = newBaseUrl
                };
                await SendJsonMessage(message);
                baseUrl = newBaseUrl;
            }
            else
            {
                MessageBox.Show("Not connected to server", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void sendButton_Click(object sender, EventArgs e)
        {
            SendMessage();
        }

        private void sendImageButton_Click(object sender, EventArgs e)
        {
            if (InvokeRequired)
            {
                Invoke(new Action(SendImage));
            }
            else
            {
                SendImage();
            }
        }

        private void setBaseUrlButton_Click(object sender, EventArgs e)
        {
            SetBaseUrl();
        }
    }
}