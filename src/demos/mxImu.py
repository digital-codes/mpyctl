import sys
import time
from  machine import Pin,I2C
import neopixel
import math

import mpu6886

# pins for mx atom
# Atom mx grove pins: 26 (scl),32 (sda)
# Atom mx internal i2c: 21 (scl), 25 (sda)
# internal imu address: 104 = 0x68
i2c = I2C(0,scl=Pin(21),sda=Pin(25),freq=400000)
devs = i2c.scan()
print("Devs:",devs)

imu = mpu6886.MPU6886(i2c)

p = Pin(27)
RGB = neopixel.NeoPixel(p,25)

def rgbFill(color):
    global RGB
    if RGB == None:
        return
    RGB.fill(color)
    RGB.write()


def find_abs_max_and_sign_index(a, b, c):
    # List of values to compare
    values = [a, b, c]
    
    # Calculate the absolute values and find the index of the max
    abs_values = [abs(val) for val in values]
    max_index = abs_values.index(max(abs_values))
    max_val = abs(values[max_index])

    # Determine the sign of the maximum absolute value
    if max_val > 0:
        sign = 1
    elif max_val < 0:
        sign = -1
    else:
        sign = 0

    return max_val, sign, max_index


def compute_axis_alignment_with_gravity(ax, ay, az):
    # Normalize the acceleration vector
    norm_a = math.sqrt(ax**2 + ay**2 + az**2)
    if norm_a == 0:
        return 0, 0, 0
    
    # Calculate angles with respect to the negative gravity direction
    theta_x = math.acos(-ax / norm_a)
    theta_y = math.acos(-ay / norm_a)
    theta_z = math.acos(-az / norm_a)

    # Convert radians to degrees for easier interpretation
    return math.degrees(theta_x), math.degrees(theta_y), math.degrees(theta_z)


def quaternion_from_euler(theta_x, theta_y, theta_z):
    # Helper function to compute quaternion for rotation about an axis
    def axis_angle_to_quat(angle, axis):
        w = math.cos(angle / 2.0)
        x = math.sin(angle / 2.0) * axis[0]
        y = math.sin(angle / 2.0) * axis[1]
        z = math.sin(angle / 2.0) * axis[2]
        return (w, x, y, z)

    # Convert degrees to radians
    theta_x = math.radians(theta_x)
    theta_y = math.radians(theta_y)
    theta_z = math.radians(theta_z)

    # Quaternion for each axis rotation
    qx = axis_angle_to_quat(theta_x, [1, 0, 0])
    qy = axis_angle_to_quat(theta_y, [0, 1, 0])
    qz = axis_angle_to_quat(theta_z, [0, 0, 1])

    # Function to multiply quaternions
    def multiply_quaternions(q1, q2):
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
        x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
        y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
        z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2
        return (w, x, y, z)

    # Compose rotations: quaternion multiplication is right to left for this order
    q = multiply_quaternions(qz, qy)
    q = multiply_quaternions(q, qx)
    
    return q


while True:
    acc = imu.acceleration
    #print(acc)
    #print(imu.gyro)
    m,s,i = find_abs_max_and_sign_index(*acc)
    #print(m,s,i)
    if m > 2:
        if i == 0:
            rgbFill((255,0,0))
        elif i == 1:    
            rgbFill((0,255,0))  
        else:    
            rgbFill((0,0,255))
    else:
        rgbFill((255,255,255))   
                
    theta_x, theta_y, theta_z = compute_axis_alignment_with_gravity(*acc)
    # print("Theta X:", theta_x, "Theta Y:", theta_y, "Theta Z:", theta_z)

    quaternion = quaternion_from_euler(theta_x, theta_y, theta_z)
    print("Quaternion:", quaternion)


    # print(imu.temperature)
    time.sleep(1) # .04)

