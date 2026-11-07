package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;

/** An operation's failure, as an error answer (PROTOCOL.md 6): its type, its message, its fields. */
final class ProbeException extends Exception {

	final String type;
	final JsonObject fields;

	ProbeException(String type, String message, JsonObject fields) {
		super(message);
		this.type = type;
		this.fields = fields;
	}

	static ProbeException badRequest(String field, String message) {
		JsonObject fields = new JsonObject();
		fields.addProperty("field", field);
		return new ProbeException("BadRequest", message, fields);
	}
}
