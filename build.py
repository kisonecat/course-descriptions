#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p "python3.withPackages(ps: [ps.pyaml])"

import sys
import subprocess
import yaml
import os
import tempfile
import shutil

def extract_yaml_preamble(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()
        if lines[0].strip() != "---":
            return None
        yaml_lines = []
        for line in lines[1:]:
            if line.strip() == "---":
                break
            yaml_lines.append(line)
        preamble = "\n".join(yaml_lines)
    return yaml.safe_load(preamble)

def convert_to_tex(filename):
    try:
        result = subprocess.run(["pandoc", filename, "--to", "latex", "-o", "-"],
                                capture_output=True, check=True)
        if result.returncode == 0:
            return result.stdout
        else:
            raise Exception("Failed to run pandoc.")
    except subprocess.CalledProcessError:
        print("Failed to convert to .tex with Pandoc.")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scriptname.py <filename>")
        sys.exit(1)

    filename = sys.argv[1]
    base_name, _ = os.path.splitext(filename)

    # Convert markdown to .tex using pandoc
    tex = convert_to_tex(filename).decode()

    tex = '\maketitle' + "\n\n" + tex

    tex = r'\newcommand{\coursenumber}{' + base_name + '}' + tex

    # Extract YAML preamble
    preamble = extract_yaml_preamble(filename)
    if preamble is not None:
        tex = r'\newcommand{\coursetitle}{' + preamble['title'] + '}' + tex
        tex = r'\newcommand{\semesters}{' + ', '.join(sorted(preamble['semesters'])) + '}' + tex
        if preamble['credits'] == 1:
            tex = r'\newcommand{\credits}{1 credit}' + tex
        else:
            tex = r'\newcommand{\credits}{' + str(preamble['credits']) + ' credits}' + tex
    else:
        print("No valid YAML preamble found.")

    with tempfile.NamedTemporaryFile(suffix=".tex", delete=False) as temp:
        temp_name = temp.name
        with open("header.tex", "r") as header_file:
            header_content = header_file.read()
            temp.write(header_content.encode())

        temp.write(tex.encode())

        with open("footer.tex", "r") as footer_file:
            footer_content = footer_file.read()
            temp.write(footer_content.encode())

        temp.close()

        try:
            # Compile the .tex file twice with xelatex
            subprocess.run(["xelatex", temp_name],
                           cwd=os.path.dirname(temp_name),
                           check=True)
            subprocess.run(["xelatex", temp_name],
                           cwd=os.path.dirname(temp_name),
                           check=True)            
        except subprocess.CalledProcessError:
            print("Failed to compile with xelatex.")

        # Clean up: delete the temporary .tex file (and the associated .log and .aux files)
        os.remove(temp_name)
        os.remove(os.path.splitext(temp_name)[0] + ".log")
        os.remove(os.path.splitext(temp_name)[0] + ".aux")        

        output_name = os.path.splitext(temp_name)[0] + ".pdf"
        # Combine the filename with the current directory to form the destination path
        destination_path = os.path.join(os.getcwd(), base_name + ".pdf")

        # Move the file to the current directory
        shutil.move(output_name, destination_path)
