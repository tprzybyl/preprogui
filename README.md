# preprogui
Pre-Processing Graphical User Interface (For Eyetracking Data)

You need Python 3.x installed

install command :
pip install -r requirements.txt

run command :
python3 PReProGui.py

This work-in-progress programm is used to load Eyetracking Data and Metadata, gathered from Eyelink devices.
It is able to read multiple asc files created from edf2asc (SR Research), and can read any Metadata in a JSON Format.

User can customize what variables (Position in degrees, Filtered Velocity, etc..) to compute and keep for each trial.
Then the codes puts everthing in a blender, and returns a list of python Dictionary that includes every trial from all the Data files, mixed with the Metadata.

You can then visualize the Data structure in the form of a tree, and get a first sight on plotted Data for eye pleasure!
You can export the data structure aswell as pickle, JSON, TSV or CSV. (pickle is the safest, but python only)

You can save and load presets of edfreader settings, selected Variables, loaded Data files, and loaded Metadata files.
You can customize the variables by adding them in the variables2.json, and adding your own related function in the preprocessing.py file.

Ideas welcome!

To do list:
- Make README cleaner
- An actual documentation
- no-gui mode, for advanced users, to make computation from files, using only presets

ANNA wishlist
