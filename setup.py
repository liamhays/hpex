import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="hpex",
    version="1.0.0",
    author="Liam Hays",
    author_email="liamrhays@gmail.com",
    description="HP 48 to Linux transfer tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/liamhays/hpex",
    #project_urls={
    #    "Bug Tracker": "https://github.com/pypa/sampleproject/issues",
    #},
    #classifiers=[
    #    "Programming Language :: Python :: 3",
    #    "License :: OSI Approved :: MIT License",
    #    "Operating System :: OS Independent",
    #],
    packages=['hpex'], 
    package_dir={"": "src"},
    python_requires=">=3.9",
)
