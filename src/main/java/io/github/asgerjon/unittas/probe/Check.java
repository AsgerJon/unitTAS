package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * wait.until's test (PROTOCOL.md 8.2): a comparison of an operation's value, or of the part a path points at, made
 * from JSON once and evaluated at every tick. A comparison is one of eq, ne, lt, le, gt, ge, in, contains, exists and
 * len (with a comparison inside); all, any and not combine tests. A test that isn't one of these is a BadRequest when
 * the request comes, never at a tick.
 */
abstract class Check {

	private static final String KINDS = "all, any, not, or a path with one of eq, ne, lt, le, gt, ge, in, contains,"
		+ " exists, len";

	abstract boolean holds(JsonElement value);

	/** The test the JSON describes; BadRequest (field "test") for one that is none. */
	static Check of(JsonElement json) throws ProbeException {
		if (json == null || !json.isJsonObject()) {
			throw bad("a test is an object (" + KINDS + "), not " + json);
		}
		JsonObject test = json.getAsJsonObject();
		if (test.has("all") || test.has("any")) {
			boolean all = test.has("all");
			JsonElement list = test.get(all ? "all" : "any");
			if (test.entrySet().size() != 1 || !list.isJsonArray()) {
				throw bad((all ? "all" : "any") + " takes a list of tests and nothing beside it");
			}
			List<Check> parts = new ArrayList<>();
			for (JsonElement part : list.getAsJsonArray()) {
				parts.add(of(part));
			}
			return all ? new All(parts) : new Any(parts);
		}
		if (test.has("not")) {
			if (test.entrySet().size() != 1) {
				throw bad("not takes one test and nothing beside it");
			}
			return new Not(of(test.get("not")));
		}
		List<Object> path = new ArrayList<>();
		JsonElement steps = test.get("path");
		if (steps != null) {
			if (!steps.isJsonArray()) {
				throw bad("a test's path is a list of names and indexes, not " + steps);
			}
			for (JsonElement step : steps.getAsJsonArray()) {
				if (step.isJsonPrimitive() && step.getAsJsonPrimitive().isString()) {
					path.add(step.getAsString());
				} else if (step.isJsonPrimitive() && step.getAsJsonPrimitive().isNumber()) {
					path.add(step.getAsInt());
				} else {
					throw bad("a path's step is a name or an index, not " + step);
				}
			}
		}
		Compare compare = null;
		for (Map.Entry<String, JsonElement> entry : test.entrySet()) {
			if (entry.getKey().equals("path")) {
				continue;
			}
			if (compare != null) {
				throw bad("a test makes one comparison, not " + compare.kind + " and " + entry.getKey());
			}
			compare = Compare.of(entry.getKey(), entry.getValue());
		}
		if (compare == null) {
			throw bad("a test needs a comparison (" + KINDS + ")");
		}
		return new AtPath(path, compare);
	}

	static ProbeException bad(String message) {
		return ProbeException.badRequest("test", message);
	}

	/** The part of the value the path points at, or null when there is none there. */
	static JsonElement follow(JsonElement value, List<Object> path) {
		JsonElement here = value;
		for (Object step : path) {
			if (here == null || here.isJsonNull()) {
				return null;
			}
			if (step instanceof String && here.isJsonObject()) {
				here = here.getAsJsonObject().get((String) step);
			} else if (step instanceof Integer && here.isJsonArray()) {
				JsonArray array = here.getAsJsonArray();
				int index = (Integer) step;
				here = index >= 0 && index < array.size() ? array.get(index) : null;
			} else {
				return null;
			}
		}
		return here;
	}

	private static final class AtPath extends Check {
		final List<Object> path;
		final Compare compare;

		AtPath(List<Object> path, Compare compare) {
			this.path = path;
			this.compare = compare;
		}

		@Override
		boolean holds(JsonElement value) {
			return compare.holds(follow(value, path));
		}
	}

	private static final class All extends Check {
		final List<Check> parts;

		All(List<Check> parts) {
			this.parts = parts;
		}

		@Override
		boolean holds(JsonElement value) {
			for (Check part : parts) {
				if (!part.holds(value)) {
					return false;
				}
			}
			return true;
		}
	}

	private static final class Any extends Check {
		final List<Check> parts;

		Any(List<Check> parts) {
			this.parts = parts;
		}

		@Override
		boolean holds(JsonElement value) {
			for (Check part : parts) {
				if (part.holds(value)) {
					return true;
				}
			}
			return false;
		}
	}

	private static final class Not extends Check {
		final Check part;

		Not(Check part) {
			this.part = part;
		}

		@Override
		boolean holds(JsonElement value) {
			return !part.holds(value);
		}
	}

	/** One comparison of the value found (null: nothing there). */
	private abstract static class Compare {
		final String kind;

		Compare(String kind) {
			this.kind = kind;
		}

		abstract boolean holds(JsonElement found);

		static Compare of(String kind, JsonElement with) throws ProbeException {
			switch (kind) {
				case "eq":
					return new Compare(kind) {
						@Override
						boolean holds(JsonElement found) {
							return same(found, with);
						}
					};
				case "ne":
					return new Compare(kind) {
						@Override
						boolean holds(JsonElement found) {
							return !same(found, with);
						}
					};
				case "lt":
				case "le":
				case "gt":
				case "ge":
					if (!isNumber(with)) {
						throw bad(kind + " compares with a number, not " + with);
					}
					double bound = with.getAsDouble();
					return new Compare(kind) {
						@Override
						boolean holds(JsonElement found) {
							if (!isNumber(found)) {
								return false;
							}
							double number = found.getAsDouble();
							switch (kind) {
								case "lt":
									return number < bound;
								case "le":
									return number <= bound;
								case "gt":
									return number > bound;
								default:
									return number >= bound;
							}
						}
					};
				case "in":
					if (!with.isJsonArray()) {
						throw bad("in takes a list, not " + with);
					}
					return new Compare(kind) {
						@Override
						boolean holds(JsonElement found) {
							for (JsonElement each : with.getAsJsonArray()) {
								if (same(found, each)) {
									return true;
								}
							}
							return false;
						}
					};
				case "contains":
					return new Compare(kind) {
						@Override
						boolean holds(JsonElement found) {
							if (found != null && found.isJsonArray()) {
								for (JsonElement each : found.getAsJsonArray()) {
									if (same(each, with)) {
										return true;
									}
								}
								return false;
							}
							return found != null && found.isJsonPrimitive() && found.getAsJsonPrimitive().isString()
								&& with.isJsonPrimitive() && found.getAsString().contains(with.getAsString());
						}
					};
				case "exists":
					if (!with.isJsonPrimitive() || !with.getAsJsonPrimitive().isBoolean()) {
						throw bad("exists is true or false, not " + with);
					}
					boolean wanted = with.getAsBoolean();
					return new Compare(kind) {
						@Override
						boolean holds(JsonElement found) {
							return (found != null && !found.isJsonNull()) == wanted;
						}
					};
				case "len":
					Check inner = Check.of(with);
					return new Compare(kind) {
						@Override
						boolean holds(JsonElement found) {
							Integer length = length(found);
							return length != null && inner.holds(new JsonPrimitive(length));
						}
					};
				default:
					throw bad(kind + " is no comparison (" + KINDS + ")");
			}
		}

		static boolean isNumber(JsonElement value) {
			return value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber();
		}

		/** Equal as JSON, numbers by their value (1 is 1.0). Nothing there equals only null. */
		static boolean same(JsonElement found, JsonElement with) {
			if (found == null || found.isJsonNull()) {
				return with == null || with.isJsonNull();
			}
			if (isNumber(found) && isNumber(with)) {
				return found.getAsDouble() == with.getAsDouble();
			}
			return found.equals(with);
		}

		/** A string's, a list's or an object's length; null for anything else. */
		static Integer length(JsonElement found) {
			if (found == null) {
				return null;
			}
			if (found.isJsonArray()) {
				return found.getAsJsonArray().size();
			}
			if (found.isJsonObject()) {
				return found.getAsJsonObject().entrySet().size();
			}
			if (found.isJsonPrimitive() && found.getAsJsonPrimitive().isString()) {
				return found.getAsString().length();
			}
			return null;
		}
	}
}
