from Crypto.Cipher import DES
from Crypto.Util.Padding import pad, unpad
from flask import Flask, request, render_template, send_file, jsonify, make_response, url_for
from werkzeug.utils import secure_filename
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding as rsa_padding # CORRECTED LINE
from cryptography.hazmat.primitives import serialization, hashes, padding as sym_padding
import os, io, time
import hashlib
import re

# Import the new entropy_utils module
import entropy_utils
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Create a directory for static heatmap images
app.config['HEATMAP_FOLDER'] = os.path.join(app.root_path, 'static', 'heatmaps')
os.makedirs(app.config['HEATMAP_FOLDER'], exist_ok=True)

# Generate RSA key pair once
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

##Cipher Functions 
def caesar_encrypt(text, shift):  # Function to encrypt text using Caesar cipher with a given shift
    return ''.join(  # Join all encrypted characters into one string
        chr((ord(c) - (65 if c.isupper() else 97) + shift) % 26 + (65 if c.isupper() else 97))  # Shift the character by given value, wrap around alphabet
        if c.isalpha() else c  # Only apply cipher on alphabetic characters; keep others (e.g., spaces, punctuation) unchanged
        for c in text  # Loop through each character in the input text
    )

def caesar_decrypt(text, shift):  # Function to decrypt Caesar cipher by reversing the shift
    return caesar_encrypt(text, -shift)  # Decrypt by calling encrypt function with negative shift


##AES:
def aes_encrypt(text, key):  # Function to encrypt plaintext using AES
    key = key.encode()[:32].ljust(32, b'\0')  # Convert key to bytes, make it exactly 32 bytes (256-bit key) by padding with null bytes
    # Pad text to be a multiple of AES block size (16 bytes)
    padder = sym_padding.PKCS7(algorithms.AES.block_size).padder()  # Create a PKCS7 padder using AES block size
    padded_text = padder.update(text.encode()) + padder.finalize()  # Encode the text to bytes and apply padding

    cipher = Cipher(algorithms.AES(key), modes.CBC(b'\0' * 16), backend=default_backend())  # Create AES cipher object with key, CBC mode, and fixed IV (16 null bytes)
    encryptor = cipher.encryptor()  # Create an encryptor from the cipher
    ct = encryptor.update(padded_text) + encryptor.finalize()  # Encrypt the padded text
    return ct.hex()  # Return the encrypted bytes as a hexadecimal string

def aes_decrypt(text_hex, key):  # Function to decrypt AES ciphertext
    key = key.encode()[:32].ljust(32, b'\0')  # Convert key to bytes, make it 32 bytes with padding
    ct = bytes.fromhex(text_hex)  # Convert the hex string back to raw bytes
    cipher = Cipher(algorithms.AES(key), modes.CBC(b'\0' * 16), backend=default_backend())  # Create AES cipher with same settings used in encryption
    decryptor = cipher.decryptor()  # Create a decryptor object
    padded_text = decryptor.update(ct) + decryptor.finalize()  # Decrypt the ciphertext to get padded plaintext
    unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()  # Create an unpadder for PKCS7
    text = unpadder.update(padded_text) + unpadder.finalize()  # Remove padding from plaintext
    return text.decode('utf-8', errors='ignore')  # Convert bytes to string, ignoring any decoding errors


##RSA
def rsa_encrypt(text, public_key):  # Function to encrypt plaintext using RSA public key
    ciphertext = public_key.encrypt(  # Encrypt the text using the public key
        text.encode('utf-8'),  # Convert the text to bytes using UTF-8 encoding
        rsa_padding.OAEP(  # Use OAEP (Optimal Asymmetric Encryption Padding) for better security
            mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()),  # Mask Generation Function with SHA-256 hash
            algorithm=hashes.SHA256(),  # Main hash function used for OAEP padding
            label=None  # Optional label, not used here
        )
    )
    return ciphertext.hex()  # Return the encrypted bytes as a hexadecimal string

def rsa_decrypt(text_hex, private_key):  # Function to decrypt RSA ciphertext using private key
    plaintext = private_key.decrypt(  # Decrypt the ciphertext using the private key
        bytes.fromhex(text_hex),  # Convert the hexadecimal ciphertext back to bytes
        rsa_padding.OAEP(  # Use the same OAEP padding scheme as used in encryption
            mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()),  # Same MGF with SHA-256
            algorithm=hashes.SHA256(),  # Same main hash algorithm
            label=None  # Label should match the one used during encryption (None here)
        )
    )
    return plaintext.decode('utf-8')  # Convert the decrypted bytes back to UTF-8 string and return

##Vigener cipher
def vigenere_encrypt(text, key):  # Function to encrypt text using Vigenère cipher with a given key
    key = [ord(c.upper()) - 65 for c in key if c.isalpha()]  # Convert key to uppercase letters and map each to 0-25
    if not key:  # Check if key contains no valid alphabetic characters
        raise ValueError("Vigenère key must contain alphabetic characters.")  # Raise error if key is invalid
    key_len = len(key)  # Store length of the processed key
    encrypted_text = []  # Initialize list to store encrypted characters
    key_idx = 0  # Index to keep track of position in key
    for char in text:  # Loop through each character in the plaintext
        if 'a' <= char <= 'z':  # If character is lowercase
            shift = key[key_idx % key_len]  # Get corresponding shift value from key
            encrypted_text.append(chr(((ord(char) - ord('a') + shift) % 26) + ord('a')))  # Apply encryption and append result
            key_idx += 1  # Move to next key character
        elif 'A' <= char <= 'Z':  # If character is uppercase
            shift = key[key_idx % key_len]  # Get corresponding shift value from key
            encrypted_text.append(chr(((ord(char) - ord('A') + shift) % 26) + ord('A')))  # Apply encryption and append result
            key_idx += 1  # Move to next key character
        else:  # If character is non-alphabetic
            encrypted_text.append(char)  # Leave character unchanged
    return "".join(encrypted_text)  # Join encrypted characters into a single string and return

def vigenere_decrypt(text, key):  # Function to decrypt Vigenère cipher text with a given key
    key = [ord(c.upper()) - 65 for c in key if c.isalpha()]  # Convert key to uppercase and map to 0-25
    if not key:  # Check if key is empty
        raise ValueError("Vigenère key must contain alphabetic characters.")  # Raise error for invalid key
    key_len = len(key)  # Get length of key
    decrypted_text = []  # Initialize list to store decrypted characters
    key_idx = 0  # Index to keep track of key position
    for char in text:  # Loop through each character in the ciphertext
        if 'a' <= char <= 'z':  # If character is lowercase
            shift = key[key_idx % key_len]  # Get shift value
            decrypted_text.append(chr(((ord(char) - ord('a') - shift + 26) % 26) + ord('a')))  # Apply decryption and append result
            key_idx += 1  # Move to next key character
        elif 'A' <= char <= 'Z':  # If character is uppercase
            shift = key[key_idx % key_len]  # Get shift value
            decrypted_text.append(chr(((ord(char) - ord('A') - shift + 26) % 26) + ord('A')))  # Apply decryption and append result
            key_idx += 1  # Move to next key character
        else:  # If character is not a letter
            decrypted_text.append(char)  # Leave it unchanged
    return "".join(decrypted_text)  # Return the final decrypted string

##DES:
def des_encrypt(text, key):
    key = key.encode()[:8].ljust(8, b'\0')  # Make key exactly 8 bytes
    cipher = DES.new(key, DES.MODE_ECB)    # Create DES cipher in ECB mode
    padded_text = pad(text.encode(), DES.block_size)  # Pad text to 8 bytes
    ct_bytes = cipher.encrypt(padded_text)
    return ct_bytes.hex()  # Return ciphertext in hex


def des_decrypt(text_hex, key):
    key = key.encode()[:8].ljust(8, b'\0')  # Make key exactly 8 bytes
    cipher = DES.new(key, DES.MODE_ECB)    # Same cipher for decryption
    ct = bytes.fromhex(text_hex)           # Convert hex back to bytes
    decrypted_padded = cipher.decrypt(ct)
    decrypted = unpad(decrypted_padded, DES.block_size)  # Remove padding
    return decrypted.decode('utf-8', errors='ignore')     # Return string


# Mapping of methods to their encryption/decryption functions
ALGORITHMS = {
    'caesar': {'encrypt': caesar_encrypt, 'decrypt': caesar_decrypt},
    'aes': {'encrypt': aes_encrypt, 'decrypt': aes_decrypt},
    'rsa': {'encrypt': rsa_encrypt, 'decrypt': rsa_decrypt},
    'vigenere': {'encrypt': vigenere_encrypt, 'decrypt': vigenere_decrypt},
    'des': {'encrypt': des_encrypt, 'decrypt': des_decrypt}
}

def transform_content(content, method, operation, key, shift):
    func = ALGORITHMS[method][operation]
    if method == 'caesar' or method == 'vigenere':
        return func(content, shift if method == 'caesar' else key)
    elif method == 'aes' or method == 'des':
        return func(content, key)
    elif method == 'rsa':
        if operation == 'encrypt':
            return func(content, public_key)
        else: # decrypt
            return func(content, private_key)
    else:
        raise ValueError("Invalid method or operation")


# ========== Flask Routes ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/encrypt')
def encrypt_page():
    return render_template('encrypt.html')

@app.route('/decrypt')
def decrypt_page():
    return render_template('decrypt.html')

@app.route('/performance')
def performance_page():
    return render_template('performance.html')

@app.route('/entropy_analyzer')
def entropy_analyzer_page():
    return render_template('entropy_analyzer.html')

@app.route('/hashing_tool')
def hashing_tool_page():
    return render_template('hashing_tool.html')

@app.route('/password_strength')
def password_strength_page():
    return render_template('password_strength.html')


@app.route('/process', methods=['POST'])
def process():
    try:
        file = request.files['file']
        if file.filename == '':
            return "<h3>Error: No file selected</h3>", 400

        method = request.form['method']
        operation = request.form['operation']
        key = request.form.get('key', 'default_key')
        shift_str = request.form.get('shift', '3')
        shift = int(shift_str) if shift_str.strip().isdigit() else 3

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        with open(filepath, 'rb') as f: # Read as bytes for better compatibility
            raw_content = f.read()
        try:
            content = raw_content.decode('utf-8')
        except UnicodeDecodeError:
            content = raw_content.decode('latin1') # Fallback for non-UTF-8 content

        st = time.time()
        result_content = transform_content(content, method, operation, key, shift)
        elapsed = (time.time() - st) * 1000 # No rounding, or round to desired precision for display

        # For demonstration, let's ensure result_content is a string for display
        if isinstance(result_content, bytes):
            result_content = result_content.hex() # Display bytes as hex string

        # Save result file - handle binary vs text results
        result_filename = f"{operation}_{filename}"
        result_path = os.path.join(app.config['UPLOAD_FOLDER'], result_filename)
        if isinstance(result_content, str):
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write(result_content)
        elif isinstance(result_content, bytes):
            with open(result_path, 'wb') as f: # Write as binary if bytes
                f.write(result_content)


        return render_template('result.html',
                               operation=operation.capitalize(),
                               method=method.upper(),
                               filename=result_filename, # Changed to result_filename for download
                               elapsed=f"{elapsed:.6f}", # Display with 6 decimal places for precision
                               result=result_content)
    except Exception as e:
        return f"<h3>Error: {str(e)}</h3>", 400

@app.route('/download/<filename>')
def download(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(path, as_attachment=True)

@app.route('/performance_check_json', methods=['POST'])
def performance_check_json():
    try:
        file = request.files['file']
        operation = request.form['operation']
        key = request.form.get('key', 'key')
        shift_str = request.form.get('shift', '3')
        shift = int(shift_str) if shift_str.isdigit() else 3

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        with open(filepath, 'rb') as f:
            raw = f.read()
        try:
            content = raw.decode('utf-8')
        except UnicodeDecodeError:
            content = raw.decode('latin1')

        results = {}
        for m in ['caesar', 'aes', 'rsa', 'vigenere', 'des']:
            try:
                st = time.time()
                # Pass a dummy key if not provided, to prevent errors for AES/DES/Vigenere when benchmarking
                current_key = key if m in ['aes', 'rsa', 'vigenere', 'des'] and key else 'default_key'
                _ = transform_content(content, m, operation, current_key, shift)
                elapsed = (time.time() - st) * 1000
                results[m.upper()] = f"{elapsed:.6f}" # Format for display
            except Exception as algo_e:
                results[m.upper()] = f"Error: {str(algo_e)}"
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/analyze_entropy_json', methods=['POST'])
def analyze_entropy_json():
    try:
        generator_type = request.form['rng_type']
        sample_size = int(request.form['sample_size'])

        data = entropy_utils.generate_samples(generator_type, sample_size)
        byte_entropy = entropy_utils.shannon_entropy(data)
        bit_entropy = entropy_utils.bit_level_entropy(data)

        # Prepare data for distribution chart (frequency of each byte value)
        counts = entropy_utils.Counter(data)
        labels = [str(i) for i in range(256)] # All possible byte values
        frequencies = [counts[i] for i in range(256)]

        return jsonify({
            "byte_entropy": f"{byte_entropy:.4f}",
            "bit_entropy": f"{bit_entropy:.4f}",
            "security_rating": "Secure ✅" if byte_entropy > 7.5 else "Weak ❌",
            "distribution_data": {
                "labels": labels,
                "data": frequencies
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/compare_rngs_json', methods=['POST'])
def compare_rngs_json():
    try:
        sample_size = int(request.form['sample_size'])
        rng_types = ["random", "numpy", "secrets"] # Or a list from frontend if allowed to select

        results = {}
        for gen_type in rng_types:
            try:
                data = entropy_utils.generate_samples(gen_type, sample_size)
                results[gen_type.capitalize()] = entropy_utils.shannon_entropy(data)
            except ImportError as ie:
                results[gen_type.capitalize()] = f"Error: {str(ie)}"
            except Exception as e:
                results[gen_type.capitalize()] = f"Error processing {gen_type}: {str(e)}"

        # Prepare data for comparison chart
        labels = list(results.keys())
        entropy_values = list(results.values())

        return jsonify({
            "comparison_data": {
                "labels": labels,
                "data": entropy_values
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/generate_heatmap', methods=['POST'])
def generate_heatmap():
    try:
        generator_type = request.form['rng_type']
        sample_size = int(request.form['sample_size'])

        data = entropy_utils.generate_samples(generator_type, sample_size)
        # For heatmap, we often take a smaller slice for visualization if sample_size is very large
        # Let's limit to first 1000 bytes for practical visualization
        display_data = data[:min(sample_size, 1000)]
        bits = np.array([[int(b) for b in f"{byte:08b}"] for byte in display_data])

        plt.figure(figsize=(12, max(3, len(display_data) // 100))) # Adjust figure size dynamically
        sns.heatmap(bits.T, cmap="viridis", cbar=False, yticklabels=[str(i) for i in range(8)]) # Use viridis for better contrast, yticklabels for bits
        plt.title(f"Bit-Level Entropy Heatmap for {generator_type.capitalize()} (First {len(display_data)} Bytes)")
        plt.xlabel("Byte Index")
        plt.ylabel("Bit Position")
        plt.tight_layout()

        # Save plot to a temporary file
        heatmap_filename = f"{generator_type}_heatmap_{int(time.time())}.png"
        heatmap_filepath = os.path.join(app.config['HEATMAP_FOLDER'], heatmap_filename)
        plt.savefig(heatmap_filepath)
        plt.close() # Close the plot to free memory

        return jsonify({"heatmap_url": url_for('static', filename=f'heatmaps/{heatmap_filename}')})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/calculate_file_hash', methods=['POST'])
def calculate_file_hash():
    try:
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected."}), 400

        # Read the file in chunks to handle large files efficiently
        hasher = hashlib.sha256() # Using SHA256 as a default, strong hash
        for chunk in iter(lambda: file.read(4096), b''): # Read in 4KB chunks
            hasher.update(chunk)

        file_hash = hasher.hexdigest()
        return jsonify({"hash": file_hash})

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/check_password_strength_json', methods=['POST'])
def check_password_strength_json():
    password = request.form.get('password', '')
    strength_score = 0
    feedback = []

    # Rule 1: Length (min 8 characters)
    if len(password) >= 8:
        strength_score += 1
        feedback.append("✅ At least 8 characters long")
    else:
        feedback.append("❌ Must be at least 8 characters long")

    # Rule 2: Contains uppercase letters
    if re.search(r'[A-Z]', password):
        strength_score += 1
        feedback.append("✅ Contains uppercase letters")
    else:
        feedback.append("❌ Add uppercase letters")

    # Rule 3: Contains lowercase letters
    if re.search(r'[a-z]', password):
        strength_score += 1
        feedback.append("✅ Contains lowercase letters")
    else:
        feedback.append("❌ Add lowercase letters")

    # Rule 4: Contains numbers
    if re.search(r'[0-9]', password):
        strength_score += 1
        feedback.append("✅ Contains numbers")
    else:
        feedback.append("❌ Add numbers")

    # Rule 5: Contains special characters
    if re.search(r'[^a-zA-Z0-9]', password):
        strength_score += 1
        feedback.append("✅ Contains special characters")
    else:
        feedback.append("❌ Add special characters")

    # Determine overall strength based on score
    overall_strength = "Very Weak"
    strength_color = "#f44336" # Red
    if strength_score == 5:
        overall_strength = "Very Strong"
        strength_color = "#4CAF50" # Green
    elif strength_score >= 3:
        overall_strength = "Moderate"
        strength_color = "#ffeb3b" # Yellow
    elif strength_score >= 1:
        overall_strength = "Weak"
        strength_color = "#ff9800" # Orange

    return jsonify({
        "strength_score": strength_score,
        "overall_strength": overall_strength,
        "strength_color": strength_color,
        "feedback": feedback
    })


if __name__ == '__main__':
    app.run(debug=True)