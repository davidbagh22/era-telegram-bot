export {};

declare global {
  interface ObjectConstructor {
    hasOwn(object: object, propertyKey: PropertyKey): boolean;
  }
}
