const int pinSensor = A0; // Pin conectado al pin de salida del SS49E

void setup() {
  Serial.begin(9600);
}

void loop() {
  int lecturaBits = analogRead(pinSensor); // Lee entre 0 y 1023 (en Arduino Uno)
  
  // MAPEO DE VALORES (Debes ajustar "MinBits" y "MaxBits" en tu calibración)
  // Ejemplo ficticio: vacío mide 320 bits y lleno mide 780 bits.
  int porcentajeTanque = map(lecturaBits, 320, 780, 0, 100); 
  
  // Limitar los valores entre 0% y 100% para evitar errores fuera de rango
  porcentajeTanque = constrain(porcentajeTanque, 0, 100);

  Serial.print("Lectura Cruda (Bits): ");
  Serial.print(lecturaBits);
  Serial.print("  |  Nivel del Tanque: ");
  Serial.print(porcentajeTanque);
  Serial.println("%");

  delay(1000); // Lee el tanque cada segundo
}
