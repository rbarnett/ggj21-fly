import cx_Freeze
# Change "App" to the name of your python script
executables = [cx_Freeze.Executable("fly.py")]

cx_Freeze.setup(
    name="Fly",
    version = "1",
    options={"build_exe": {"packages":["pyglet", "cocos"]}},
    executables = executables
    )