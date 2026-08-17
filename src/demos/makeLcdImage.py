from PIL import Image
import numpy as np
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-i","--input", required=True,help="Input Image")
parser.add_argument("-o","--output", required=True,help="Output Image")
parser.add_argument("-r","--reversed", default=None,help="Reversed Image")

args = parser.parse_args()

# Open the BMP image
img = Image.open(args.input)
rgb_img = img.convert('RGB')
imgArr = np.array(rgb_img)
imgShape = imgArr.shape
print("Input shape:",imgShape)
# check if r,g,b values are in 0..1 range or 0..255 range
if np.max(imgArr) <= 1.0:
    print("Input image values are in 0..1 range, converting to 0..255 range")
    imgArr = (imgArr * 255).astype(np.uint8)
else:
    print("Input image values are in 0..255 range")
    # print max for r,g,b seprately to allow brigtness adjustment if needed
    print("Max R:",np.max(imgArr[:,:,0]))
    print("Max G:",np.max(imgArr[:,:,1]))
    print("Max B:",np.max(imgArr[:,:,2]))
# create target array
outArr = np.zeros((imgShape[0],imgShape[1]),dtype=np.uint16)

#def rgb565(r,g,b):
#...     return (r & 0xf8) << 8 | (g & 0xfc) << 3 | b >> 3

for y in range(imgShape[0]):
    for x in range(imgShape[1]):
        r,g,b = imgArr[y,x]
        outArr[y,x] = np.uint16(((np.uint16(r) & 0xf8) << 8) | ((np.uint16(g) & 0xfc) << 3) | (np.uint16(b) >> 3))
        
print("Output shape: ",outArr.shape)

outArr.tofile(args.output)
print("Output written to ",args.output)

if args.reversed:
    # generate the reverse image from the color encoded
    revImg = np.zeros((imgShape[0],imgShape[1],3),dtype=np.uint8)
    for y in range(imgShape[0]):
        for x in range(imgShape[1]):
            rgb565 = np.uint16(outArr[y,x])
            revImg[y][x][0] = (((rgb565 >> 8) & 0xfff8) << 0)
            revImg[y][x][1] = (((rgb565 >> 5) & 0xfffc) << 2)
            revImg[y][x][2] = ((rgb565 & 0x1f) << 3)
    # make sure to save the reversed image as a RGB PNG or BMP to avoid compression artifacts
    rev = Image.fromarray(revImg)
    rev.convert('RGB').save(args.reversed)
    print("Reversed image written to ",args.reversed)
    


""" Read like so:
def read_shorts_binary(filename, rows=100, cols=100):
    global imgBuf
    with open(filename, 'rb') as f:
        num_elements = rows * cols
        
        # Read all bytes at once
        raw_bytes = f.read(num_elements * 2)  # 2 bytes per int16
        
        # Unpack all values (little-endian signed short '<h')
        # make sure to have < and > right. use < on esp32 when generating with x86 linux
        values = struct.unpack('<' + 'H' * num_elements, raw_bytes)
        
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
