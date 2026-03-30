from flask import Flask, jsonify
import requests

app = Flask(__name__)

@app.route('/exchange_rates', methods=['GET'])
def exchange_rates():
    # Call the Bluelytics API
    response = requests.get('https://api.bluelytics.com.ar/json/blue_rate/last')
    data = response.json()

    # Extract the needed values
    rates = {
        'oficial': {'price': data['oficial']['value'], 'chg_pct': data['oficial']['variation']},
        'blue': {'price': data['blue']['value'], 'chg_pct': data['blue']['variation']},
        'mep': {'price': data['mep']['value'], 'chg_pct': data['mep']['variation']},
        'ccl': {'price': data['ccl']['value'], 'chg_pct': data['ccl']['variation']},
    }

    return jsonify(rates), 200
