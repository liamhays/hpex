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
    
    # Do we really need these? No. I have no plans to put HPex on
    # PyPI, which is what the classifiers are for. However, it might
    # help somebody trying to categorize HPex.
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)", 
        "Operating System :: POSIX :: Linux",
        "Natural Language :: English",
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Utilities"
    ],


    # HPex can be run with 'python -m hpex' or just 'hpex' in the
    # shell. It seems that the best way to do this is to keep the main
    # HPex dispatcher in __main__.py, then entry_points can reference
    # and instantiate that object.
    entry_points={
        'console_scripts': [
            'hpex=hpex.__main__:HPex'
        ]
    }, 
    packages=['hpex'], 
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        'wxPython',
        'xmodem',
        'pyserial',
        'PyPubSub',
        'ptyprocess'
    ]
    
        
        
)
