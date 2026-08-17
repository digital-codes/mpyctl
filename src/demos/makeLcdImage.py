from PIL import Image
import numpy as np
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-i","--input", required=True,help="Input Image")
parser.add_argument("-o","--output", required=True,help="Output Image")

args = parser.parse_args()

# Open the BMP image
img = Image.open(args.input)
rgb_img = img.convert('RGB')
imgArr = np.array(rgb_img)
imgShape = imgArr.shape
print("Input shape:",imgShape)
# create target array
outArr = np.zeros((imgShape[0],imgShape[1]),dtype=np.uint16)

#def rgb565(r,g,b):
#...     return (r & 0xf8) << 8 | (g & 0xfc) << 3 | b >> 3

for y in range(imgShape[0]):
    for x in range(imgShape[1]):
        r,g,b = imgArr[y,x]
        outArr[y,x] = np.uint16((np.uint8(r) & 0xf8) << 8 | (np.uint8(g) & 0xfc) << 3 | np.uint8(b) >> 3)
        
print("Output shape: ",outArr.shape)

outArr.tofile(args.output)
print("Written to ",args.output)

""" Read like so:
def read_shorts_binary(filename, rows=100, cols=100):
    global imgBuf
    with open(filename, 'rb') as f:
        num_elements = rows * cols
        
        # Read all bytes at once
        raw_bytes = f.read(num_elements * 2)  # 2 bytes per int16
        
        # Unpack all values (little-endian signed short '<h')
        values = struct.unpack('>' + 'H' * num_elements, raw_bytes)
        
        # Reshape into 2D list of uint16 values
        arr = [list(values[i*cols:(i+1)*cols]) for i in range(rows)]
        for y in range(100):
            for x in range(100):
                pixval = arr[y][x]
                imgBuf.append((pixval >> 8) & 0xff)
                imgBuf.append(pixval & 0xff)
    
    return imgBuf

then bit_blit buffer to display:
    
"""
