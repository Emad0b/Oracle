# Connect sensors and devices

Oracle runs on the laptop. Home Assistant bridges Arduino, Raspberry Pi and other hardware into that local workspace. Start with the existing simulated connection to try the dashboard.

1. Set up your hardware in Home Assistant. Use [ESPHome](https://www.home-assistant.io/integrations/esphome/) for supported microcontrollers, or publish your Arduino or Raspberry Pi readings through [Home Assistant MQTT](https://www.home-assistant.io/integrations/mqtt/). A USB-only Arduino needs a host bridge that reads serial data and publishes it to MQTT.
2. In Home Assistant, find the exact entity IDs for the readings and controls you want to use. Use `sensor.*` for measurements and an explicitly configured `light.*` or `switch.*` for on/off control.
3. In Oracle, open **Connections**, choose **Configure** for devices, set the backend to `home_assistant` and enter its URL and access token. Add the entity IDs as a comma-separated allowlist. The token is stored locally in `.env`.
4. In **Devices**, refresh the connection and select **Add or rename a card**. Cards show the latest available readings in Devices and Overview. **Capture readings** saves a timestamped sample for each available card. Each card retains up to 100 samples and shows the latest ten.
5. Use **Ask about this device** to draft a question, or select **Share device readings for this message** in Ask Oracle. Sending the message allows the configured AI provider to receive the requested states and recent samples. Device-aware exchanges stay out of the history automatically sent with later messages. Use the dashboard controls to confirm physical on/off changes.

Device history and card configuration are in `.data/devices.sqlite3`. Demo cards and Home Assistant cards are separate. Removing an entity from the allowlist removes its readings from the dashboard and AI tools. MyMoney remains a separate data store.
