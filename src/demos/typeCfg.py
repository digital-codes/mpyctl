""" type configuration

This module provides a TypeCfg class for configuring types.

"""

class TypeCfg:
    """TypeCfg class for configuring types.

    Attributes:
        buffer (bytearray): The buffer for storing the type configuration.
    
    Methods:
        __init__(self, type: str, version=1): Initializes a TypeCfg object.
        value(self): Returns the buffer value.
        pin(self, pin=None): Sets or gets the pin value.
        __str__(self): Returns a string representation of the TypeCfg object.

    """

    def __init__(self, type: str, version=1):
        """Initializes a TypeCfg object.

        Args:
            type (str): The type of the configuration.
            version (int, optional): The version of the configuration. Defaults to 1.

        """
        self.buffer = bytearray(10)
        self.buffer[:5] = bytes((type + " "*5)[:5].encode("utf-8")) # max 5
        self.buffer[5] = version

    def value(self):
        """Returns the buffer value.

        Returns:
            bytearray: The buffer value.

        """
        return self.buffer
        
    def pin(self, pin=None):
        """Sets or gets the pin value.

        Args:
            pin (int or bytearray, optional): The pin value to set. Defaults to None.

        Returns:
            bytearray: The pin value.

        """
        if pin != None:
            if isinstance(pin,bytearray):
                self.buffer[6:] = (pin + bytearray(4))[:4]
            else:
                try:
                    self.buffer[6:] = int.to_bytes(pin,4,"big")
                except:
                    print("Invalid pin type: integer or bytearray")
                    pass
        return self.buffer[6:]

    def __str__(self):
        """Returns a string representation of the TypeCfg object.

        Returns:
            str: The string representation of the TypeCfg object.

        """
        return " ".join([self.buffer[:5].decode("utf-8"),self.buffer[5:6].hex(),self.buffer[6:].hex()])
    
if __name__ == "__main__":
    # Create a TypeCfg object
    type_cfg = TypeCfg("test", 42)

    # Print the initial buffer value
    print("Initial buffer value: ", type_cfg.value())

    # Set and get the pin value
    pin_value = type_cfg.pin(1234)
    print("Pin value in hex: ", hex(int.from_bytes(pin_value, "big")))
    print("Pin value: ", type_cfg.pin())

    # Print the string representation of the TypeCfg object
    print("String representation: ", str(type_cfg))
    
    # Print value of the TypeCfg object
    print("Value (hex): ", type_cfg.value().hex())

