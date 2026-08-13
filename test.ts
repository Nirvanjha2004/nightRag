// calculator.ts

interface OperationResult {
  operation: string;
  result: number;
}

class Calculator {
  private history: OperationResult[] = [];

  add(a: number, b: number): number {
    const result = a + b;
    this.save("add", result);
    return result;
  }

  subtract(a: number, b: number): number {
    const result = a - b;
    this.save("subtract", result);
    return result;
  }

  multiply(a: number, b: number): number {
    const result = a * b;
    this.save("multiply", result);
    return result;
  }

  divide(a: number, b: number): number {
    if (b === 0) {
      throw new Error("Cannot divide by zero");
    }

    const result = a / b;
    this.save("divide", result);
    return result;
  }

  getHistory(): OperationResult[] {
    return this.history;
  }

  private save(operation: string, result: number): void {
    this.history.push({ operation, result });
  }
}

function greet(name: string): string {
  return `Hello, ${name}!`;
}

function isEven(value: number): boolean {
  return value % 2 === 0;
}

function sum(numbers: number[]): number {
  return numbers.reduce((acc, value) => acc + value, 0);
}

function main(): void {
  const calc = new Calculator();

  console.log(greet("Nirvan"));

  console.log(calc.add(10, 5));
  console.log(calc.subtract(20, 8));
  console.log(calc.multiply(6, 7));
  console.log(calc.divide(100, 4));

  console.log(isEven(42));
  console.log(sum([1, 2, 3, 4, 5]));

  console.log(calc.getHistory());
}

main();