export const CITIES = ["Helsinki", "Espoo", "Vantaa", "Tampere", "Turku", "Lahti"];
export const DEFAULT_CITY = "Helsinki";

export function storedCity(value) {
  return CITIES.includes(value) ? value : DEFAULT_CITY;
}
