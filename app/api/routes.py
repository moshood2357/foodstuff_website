import requests
from flask import request, jsonify, current_app
from flask_login import login_required
from . import api_bp


@api_bp.route("/lookup-address")
def lookup_address():

    postcode = request.args.get("postcode", "").strip()

    if not postcode:
        return jsonify({"error": "Postcode is required"}), 400

    api_key = current_app.config.get("IDEAL_POSTCODES_API_KEY")

    if not api_key:
        return jsonify({"error": "API key not configured"}), 500

    url = f"https://api.ideal-postcodes.co.uk/v1/postcodes/{postcode}"

    try:
        res = requests.get(url, params={"api_key": api_key}, timeout=5)
        data = res.json()

        #  API quota exhausted
        if data.get("code") == 4020:
            return jsonify({"error": "API quota exhausted"}), 503

        #  invalid postcode or failure
        if data.get("code") != 2000:
            return jsonify({"error": "Invalid postcode or no results"}), 400

        # IMPORTANT: Ideal Postcodes returns result as LIST of addresses
        results = data.get("result", [])

        addresses = []
        for r in results:
            addresses.append({
                "line_1": r.get("line_1", ""),
                "line_2": r.get("line_2", ""),
                "post_town": r.get("post_town", ""),
                "county": r.get("county", ""),
                "postcode": r.get("postcode", "")
            })

        return jsonify({"addresses": addresses})

    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500