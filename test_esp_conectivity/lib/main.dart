import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const ESP32BleConfigPage(),
    );
  }
}

class ESP32BleConfigPage extends StatefulWidget {
  const ESP32BleConfigPage({super.key});

  @override
  State<ESP32BleConfigPage> createState() => _ESP32BleConfigPageState();
}

class _ESP32BleConfigPageState extends State<ESP32BleConfigPage> {
  final _ssidController = TextEditingController();
  final _passController = TextEditingController();
  final _ipWebSocketController = TextEditingController(text: "192.168.1.XX");
  final _mensajeController = TextEditingController();

  BluetoothDevice? _targetDevice;
  BluetoothCharacteristic? _rxCharacteristic;
  bool _estaEscaneando = false;
  bool _bleConectado = false;

  WebSocketChannel? _channel;
  final List<String> _historialMensajes = [];
  bool _estaConectadoWs = false;

  // CAMBIO 1: UUIDs idénticos a los definidos en ble_manager.py (en minúsculas para Flutter)
  final String serviceUuid = "0000fff0-0000-1000-8000-00805f9b34fb";
  final String rxUuid = "0000fff1-0000-1000-8000-00805f9b34fb";

  // --- PASO 1: CONFIGURACIÓN BLE ---
  void comenzarEscaneoBLE() async {
    setState(() => _estaEscaneando = true);
    
    await FlutterBluePlus.startScan(timeout: const Duration(seconds: 5));

    FlutterBluePlus.scanResults.listen((results) async {
      for (ScanResult r in results) {
        // CAMBIO 2: Filtrar por el nombre que MicroPython expone por defecto ("ESP32_PROV")
        if (r.device.platformName == "ESP32_PROV" || r.device.platformName.contains("ESP32")) {
          await FlutterBluePlus.stopScan();
          _targetDevice = r.device;
          _conectarAlESP32Ble();
          break;
        }
      }
    });

    await Future.delayed(const Duration(seconds: 5));
    if (mounted) setState(() => _estaEscaneando = false);
  }

  void _conectarAlESP32Ble() async {
    if (_targetDevice == null) return;

    try {
      await _targetDevice!.connect();
      if (mounted) setState(() => _bleConectado = true);

      List<BluetoothService> services = await _targetDevice!.discoverServices();
      for (var service in services) {
        if (service.uuid.toString().toLowerCase() == serviceUuid) {
          for (var characteristic in service.characteristics) {
            if (characteristic.uuid.toString().toLowerCase() == rxUuid) {
              _rxCharacteristic = characteristic;
              _mostrarAlerta("BLE Conectado", "Conexión exitosa con el ESP32. Ya puedes enviar los datos.");
            }
          }
        }
      }
    } catch (e) {
      _mostrarAlerta("Error BLE", "No se pudo conectar al dispositivo.");
    }
  }

  void enviarDatosWifiPorBle() async {
    if (_rxCharacteristic == null) {
      _mostrarAlerta("Error", "Primero conéctate al ESP32 por BLE");
      return;
    }

    final ssid = _ssidController.text.trim();
    final pass = _passController.text.trim();
    
    // CAMBIO 3: Tu MicroPython espera "SSID,PASSWORD" usando una coma en lugar de un punto y coma.
    final payload = "$ssid,$pass";

    try {
      await _rxCharacteristic!.write(utf8.encode(payload));
      _mostrarAlerta("Datos Enviados", "El ESP32 está verificando las credenciales. Si son correctas, se guardarán.");
      
      await _targetDevice?.disconnect();
      if (mounted) {
        setState(() {
          _bleConectado = false;
          _rxCharacteristic = null;
        });
      }
    } catch (e) {
      _mostrarAlerta("Error de envío", "Falló la escritura de datos vía Bluetooth.");
    }
  }

  // --- PASO 2: WEBSOCKETS ---
  void conectarWebSocket() {
    final ip = _ipWebSocketController.text.trim();
    if (ip.isEmpty) return;

    try {
      _channel = WebSocketChannel.connect(Uri.parse('ws://$ip:8765'));
      
      _channel!.stream.listen((mensaje) {
        if (mounted) {
          setState(() {
            _historialMensajes.add("ESP32: $mensaje");
          });
        }
      }, onDone: () {
        if (mounted) setState(() => _estaConectadoWs = false);
      }, onError: (error) {
        if (mounted) setState(() => _estaConectadoWs = false);
      });

      setState(() => _estaConectadoWs = true);
    } catch (e) {
      _mostrarAlerta("Error WS", "No se pudo abrir el canal WebSocket.");
    }
  }

  void enviarMensajeWebSocket() {
    if (_channel != null && _mensajeController.text.isNotEmpty) {
      _channel!.sink.add(_mensajeController.text);
      setState(() {
        _historialMensajes.add("Tú: ${_mensajeController.text}");
      });
      _mensajeController.clear();
    }
  }

  void _mostrarAlerta(String titulo, String mensaje) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(titulo),
        content: Text(mensaje),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text("OK"))],
      ),
    );
  }

  @override
  void dispose() {
    _channel?.sink.close();
    _targetDevice?.disconnect();
    _ssidController.dispose();
    _passController.dispose();
    _ipWebSocketController.dispose();
    _mensajeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("ESP32 Config por BLE")),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text("1. Configuración por Bluetooth", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            ElevatedButton(
              onPressed: _bleConectado ? null : comenzarEscaneoBLE,
              child: Text(_estaEscaneando ? "Buscando ESP32..." : _bleConectado ? "¡ESP32 Vinculado!" : "Buscar y Conectar ESP32"),
            ),
            const SizedBox(height: 10),
            TextField(controller: _ssidController, decoration: const InputDecoration(labelText: "Nombre del WiFi (SSID)")),
            TextField(controller: _passController, decoration: const InputDecoration(labelText: "Contraseña WiFi"), obscureText: true),
            const SizedBox(height: 10),
            ElevatedButton(onPressed: _bleConectado ? enviarDatosWifiPorBle : null, child: const Text("Enviar WiFi por BLE")),
            const Divider(height: 40),
            const Text("2. Operación vía WebSocket", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            TextField(controller: _ipWebSocketController, decoration: const InputDecoration(labelText: "IP Asignada al ESP32")),
            const SizedBox(height: 10),
            ElevatedButton(
              onPressed: conectarWebSocket,
              style: ElevatedButton.styleFrom(backgroundColor: _estaConectadoWs ? Colors.green : Colors.blue),
              child: Text(_estaConectadoWs ? "WebSocket Activo" : "Conectar WebSocket"),
            ),
            if (_estaConectadoWs) ...[
              const SizedBox(height: 20),
              TextField(controller: _mensajeController, decoration: const InputDecoration(labelText: "Mensaje en tiempo real")),
              ElevatedButton(onPressed: enviarMensajeWebSocket, child: const Text("Enviar Comando")),
              const SizedBox(height: 15),
              Container(
                height: 120,
                color: Colors.black12,
                child: ListView.builder(
                  itemCount: _historialMensajes.length,
                  itemBuilder: (context, index) => Padding(
                    padding: const EdgeInsets.all(4.0),
                    child: Text(_historialMensajes[index]),
                  ),
                ),
              )
            ]
          ],
        ),
      ),
    );
  }
}