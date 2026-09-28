import os
import socket
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from http.server import BaseHTTPRequestHandler, HTTPServer
import qrcode
from PIL import Image, ImageTk

shared_folder = ""
server = None


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Wi-Fi File Share</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f2f4f7;
            padding: 20px;
            text-align: center;
        }

        .box {
            max-width: 600px;
            margin: auto;
            background: white;
            padding: 25px;
            border-radius: 14px;
            box-shadow: 0 3px 12px #bbb;
        }

        input, button {
            width: 100%;
            padding: 13px;
            margin: 8px 0;
            font-size: 16px;
            box-sizing: border-box;
        }

        button {
            background: #1677ff;
            color: white;
            border: none;
            border-radius: 7px;
            cursor: pointer;
        }

        button:disabled {
            background: #999;
        }

        .progress-container {
            display: none;
            margin-top: 20px;
            text-align: left;
        }

        progress {
            width: 100%;
            height: 25px;
        }

        #status {
            margin-top: 10px;
            color: #333;
        }

        .file-name {
            text-align: left;
            padding: 5px;
            font-size: 14px;
        }
    </style>
</head>

<body>
    <div class="box">
        <h2>Upload Files</h2>

        <input type="file" id="files" multiple>

        <div id="selectedFiles"></div>

        <button id="uploadButton" onclick="uploadFiles()">
            Upload Files
        </button>

        <div class="progress-container" id="progressBox">
            <progress id="progressBar" value="0" max="100"></progress>
            <div id="status">Preparing upload...</div>
        </div>
    </div>

    <script>
        const fileInput = document.getElementById("files");
        const selectedFiles = document.getElementById("selectedFiles");

        fileInput.addEventListener("change", function () {
            selectedFiles.innerHTML = "";

            for (const file of fileInput.files) {
                const div = document.createElement("div");
                div.className = "file-name";
                div.textContent =
                    file.name + " (" + formatBytes(file.size) + ")";
                selectedFiles.appendChild(div);
            }
        });

        function formatBytes(bytes) {
            if (bytes === 0) return "0 Bytes";

            const units = ["Bytes", "KB", "MB", "GB"];
            const index = Math.floor(Math.log(bytes) / Math.log(1024));

            return (
                parseFloat((bytes / Math.pow(1024, index)).toFixed(2))
                + " "
                + units[index]
            );
        }

        function uploadFiles() {
            const files = fileInput.files;

            if (files.length === 0) {
                alert("Please select at least one file.");
                return;
            }

            const formData = new FormData();

            for (const file of files) {
                formData.append("files", file);
            }

            const xhr = new XMLHttpRequest();

            xhr.open("POST", "/upload", true);

            document.getElementById("progressBox").style.display = "block";

            const uploadButton = document.getElementById("uploadButton");
            uploadButton.disabled = true;

            xhr.upload.addEventListener("progress", function (event) {
                if (event.lengthComputable) {
                    const percent = Math.round(
                        (event.loaded / event.total) * 100
                    );

                    document.getElementById("progressBar").value = percent;

                    document.getElementById("status").textContent =
                        "Uploading: " + percent + "%";
                }
            });

            xhr.onload = function () {
                uploadButton.disabled = false;

                if (xhr.status === 200) {
                    document.getElementById("progressBar").value = 100;
                    document.getElementById("status").textContent =
                        "Upload completed successfully.";

                    fileInput.value = "";
                    selectedFiles.innerHTML = "";
                } else {
                    document.getElementById("status").textContent =
                        "Upload failed.";
                }
            };

            xhr.onerror = function () {
                uploadButton.disabled = false;
                document.getElementById("status").textContent =
                    "Network error occurred.";
            };

            xhr.send(formData);
        }
    </script>
</body>
</html>
"""


class FileShareHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            content = HTML_PAGE.encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        else:
            self.send_error(404, "Page not found")

    def do_POST(self):
        if self.path != "/upload":
            self.send_error(404, "Upload endpoint not found")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")

        if "boundary=" not in content_type:
            self.send_error(400, "Invalid multipart form data")
            return

        boundary = content_type.split("boundary=", 1)[1]
        boundary = boundary.strip('"').encode()

        body = self.rfile.read(content_length)

        parts = body.split(b"--" + boundary)
        uploaded_count = 0

        for part in parts:
            if b"filename=" not in part:
                continue

            header_end = part.find(b"\r\n\r\n")

            if header_end == -1:
                continue

            headers = part[:header_end].decode(
                "utf-8",
                errors="ignore"
            )

            file_data = part[header_end + 4:]

            file_data = file_data.rstrip(b"\r\n-")

            filename_start = headers.find('filename="')

            if filename_start == -1:
                continue

            filename_start += len('filename="')
            filename_end = headers.find('"', filename_start)

            filename = headers[filename_start:filename_end]

            # Prevent unsafe paths such as ../../file.txt
            filename = os.path.basename(filename)

            if not filename:
                continue

            save_path = os.path.join(shared_folder, filename)

            # Prevent overwriting an existing file
            base, extension = os.path.splitext(filename)
            counter = 1

            while os.path.exists(save_path):
                new_filename = f"{base}_{counter}{extension}"
                save_path = os.path.join(shared_folder, new_filename)
                counter += 1

            with open(save_path, "wb") as file:
                file.write(file_data)

            uploaded_count += 1

        response = f"{uploaded_count} file(s) uploaded successfully."

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(response.encode())))
        self.end_headers()
        self.wfile.write(response.encode())


def run_server(port=8000):
    global server

    server = HTTPServer(("0.0.0.0", port), FileShareHandler)
    server.serve_forever()


def choose_folder():
    global shared_folder

    folder = filedialog.askdirectory()

    if folder:
        shared_folder = folder
        folder_label.config(text=shared_folder)


def start_server():
    if not shared_folder:
        messagebox.showwarning(
            "Folder required",
            "Please choose a folder first."
        )
        return

    ip = get_local_ip()
    port = 8000
    url = f"http://{ip}:{port}"

    threading.Thread(
        target=run_server,
        args=(port,),
        daemon=True
    ).start()

    qr = qrcode.make(url)
    qr.save("wifi_share_qr.png")

    qr_image = Image.open("wifi_share_qr.png")
    qr_image = qr_image.resize((220, 220))

    qr_photo = ImageTk.PhotoImage(qr_image)
    qr_label.config(image=qr_photo)
    qr_label.image = qr_photo

    url_label.config(text=url)

    start_button.config(state=tk.DISABLED)
    messagebox.showinfo(
        "Server started",
        f"Open this address on another device:\n{url}"
    )


root = tk.Tk()
root.title("Wi-Fi File Share")
root.geometry("450x550")

title_label = tk.Label(
    root,
    text="Wi-Fi File Share",
    font=("Arial", 20, "bold")
)
title_label.pack(pady=15)

choose_button = tk.Button(
    root,
    text="Choose Shared Folder",
    command=choose_folder
)
choose_button.pack(pady=8)

folder_label = tk.Label(
    root,
    text="No folder selected",
    wraplength=400
)
folder_label.pack(pady=8)

start_button = tk.Button(
    root,
    text="Start Server",
    command=start_server
)
start_button.pack(pady=8)

url_label = tk.Label(
    root,
    text="Server not started",
    fg="blue"
)
url_label.pack(pady=8)

qr_label = tk.Label(root)
qr_label.pack(pady=15)

root.mainloop()
