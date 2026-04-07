# simple_calculator.py

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        return "Cannot divide by zero"
    return a / b


if __name__ == "__main__":
    print("Simple Calculator Test")

    x = 10
    y = 5

    print(f"Add: {add(x, y)}")
    print(f"Subtract: {subtract(x, y)}")
    print(f"Multiply: {multiply(x, y)}")
    print(f"Divide: {divide(x, y)}")