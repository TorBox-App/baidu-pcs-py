from setuptools import setup, find_packages, Extension
import glob
import os

def find_pyx_files():
    """Find all .pyx files and create proper module names"""
    pyx_files = []
    extensions = []
    
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith(".pyx"):
                pyx_path = os.path.join(root, file)
                # Convert file path to module name
                # e.g., ./baidupcs_py/common/simple_cipher.pyx -> baidupcs_py.common.simple_cipher
                module_name = pyx_path.replace("./", "").replace("/", ".").replace("\\", ".").replace(".pyx", "")
                
                extensions.append(Extension(
                    name=module_name,
                    sources=[pyx_path]
                ))
                pyx_files.append(pyx_path)
    
    return extensions, pyx_files

if __name__ == "__main__":
    try:
        from Cython.Build import cythonize
        extensions, pyx_files = find_pyx_files()
        
        if extensions:
            print(f"Found {len(extensions)} .pyx files to compile:")
            for ext in extensions:
                print(f"  - {ext.name}")
            
            ext_modules = cythonize(extensions, compiler_directives={'language_level': 3})
        else:
            ext_modules = []
            
    except ImportError:
        print("Cython not found. Installing without compiled extensions.")
        print("Run 'pip install Cython' and reinstall to compile .pyx files.")
        ext_modules = []
    
    setup(
        name="baidupcs-py", 
        version="0.7.6", 
        packages=find_packages(exclude=["imgs"]), 
        ext_modules=ext_modules,
        zip_safe=False,  # Required for compiled extensions
        install_requires=[
            "Cython",  # Add Cython as a dependency
        ],
        setup_requires=[
            "Cython",  # Required during setup
        ],
        # Keep package_data as fallback for source distribution
        include_package_data=True,
    )
