#pragma once

// Devuelve true si la IMU se inicializó y se pudo leer.
// Con USE_IMU=0 estas funciones no tocan el hardware y devuelven false.
bool imuBegin();
bool imuRead(float& roll, float& pitch);
