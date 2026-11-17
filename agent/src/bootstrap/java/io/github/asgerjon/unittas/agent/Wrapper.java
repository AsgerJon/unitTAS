package io.github.asgerjon.unittas.agent;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * A hooked method's wrapper (SPEC.md 19.7 step 6a): the method the game calls by the hooked one's name, put in its
 * place. Its code calls each BEFORE hook and returns the hook's value at once unless that is the pass mark, then calls
 * the original (renamed, private), then each AFTER hook, and returns what the original returned. The original's own
 * code is never touched, so its stack maps, branches and exception tables stay as they were; the wrapper's are its
 * own, one stack map frame for each BEFORE hook's "go on". The code names JDK classes only (see Rewriter): the bridge
 * is a BiFunction in the system properties (Bridge.HOOKS), the pass mark beside it (Bridge.PASS); each hook's call
 * gives it the hook's name and [the hooked class, the instance or null, the arguments, boxed].
 */
final class Wrapper {

	private static final int ACONST_NULL = 0x01;
	private static final int ICONST_0 = 0x03;
	private static final int BIPUSH = 0x10;
	private static final int SIPUSH = 0x11;
	private static final int LDC_W = 0x13;
	private static final int ILOAD = 0x15;
	private static final int LLOAD = 0x16;
	private static final int FLOAD = 0x17;
	private static final int DLOAD = 0x18;
	private static final int ALOAD = 0x19;
	private static final int AASTORE = 0x53;
	private static final int POP = 0x57;
	private static final int DUP = 0x59;
	private static final int IF_ACMPEQ = 0xA5;
	private static final int IRETURN = 0xAC;
	private static final int LRETURN = 0xAD;
	private static final int FRETURN = 0xAE;
	private static final int DRETURN = 0xAF;
	private static final int ARETURN = 0xB0;
	private static final int RETURN = 0xB1;
	private static final int INVOKEVIRTUAL = 0xB6;
	private static final int INVOKESPECIAL = 0xB7;
	private static final int INVOKESTATIC = 0xB8;
	private static final int INVOKEINTERFACE = 0xB9;
	private static final int ANEWARRAY = 0xBD;
	private static final int CHECKCAST = 0xC0;
	/** A stack map frame with the method's starting locals and one Object on the stack (JVMS 4.7.4). */
	private static final int SAME_LOCALS_1_STACK_ITEM = 64;
	private static final int SAME_LOCALS_1_STACK_ITEM_EXTENDED = 247;
	private static final int ITEM_OBJECT = 7;

	private static final String OBJECT = "java/lang/Object";
	private static final String FUNCTION = "java/util/function/BiFunction";

	private final ClassBytes file;
	private final boolean statics;
	private final List<String> parameters;
	private final String returned;
	private final byte[] code = new byte[0x10000];
	private int length;
	private final List<Integer> frames = new ArrayList<>();

	private Wrapper(ClassBytes file, boolean statics, String descriptor) {
		this.file = file;
		this.statics = statics;
		this.parameters = parameters(descriptor);
		this.returned = descriptor.substring(descriptor.indexOf(')') + 1);
	}

	/**
	 * The original renamed and made private (its code and nothing else kept on it), and its wrapper made: the
	 * original's name, descriptor and access, and every attribute of the original's but its code.
	 */
	static ClassBytes.Method wrap(ClassBytes file, ClassBytes.Method original, String renamed,
		List<Hooks.Hook> before, List<Hooks.Hook> after) {
		String descriptor = file.utf8(original.descriptor);
		Wrapper wrapper = new Wrapper(file, (original.access & ClassBytes.STATIC) != 0, descriptor);
		for (Hooks.Hook hook : before) {
			wrapper.before(hook);
		}
		wrapper.original(file.name(), renamed, descriptor);
		for (Hooks.Hook hook : after) {
			wrapper.call(hook);
			wrapper.u1(POP);
		}
		wrapper.returnAs(wrapper.returned);
		List<ClassBytes.Attribute> its = new ArrayList<>();
		List<ClassBytes.Attribute> kept = new ArrayList<>();
		int codeName = file.utf8("Code");
		its.add(new ClassBytes.Attribute(codeName, wrapper.codeAttribute()));
		for (ClassBytes.Attribute attribute : original.attributes) {
			(file.utf8(attribute.name()).equals("Code") ? kept : its).add(attribute);
		}
		ClassBytes.Method made = new ClassBytes.Method(original.access, original.name, original.descriptor, its);
		original.attributes.clear();
		original.attributes.addAll(kept);
		original.name = file.utf8(renamed);
		original.access = (original.access & ~(ClassBytes.PUBLIC | ClassBytes.PROTECTED)) | ClassBytes.PRIVATE
			| ClassBytes.SYNTHETIC;
		return made;
	}

	/** Each parameter's descriptor, in order: "(JLjava/lang/String;[I)V" gives J, Ljava/lang/String;, [I. */
	static List<String> parameters(String descriptor) {
		List<String> found = new ArrayList<>();
		int at = 1;
		while (descriptor.charAt(at) != ')') {
			int start = at;
			while (descriptor.charAt(at) == '[') {
				at++;
			}
			if (descriptor.charAt(at) == 'L') {
				at = descriptor.indexOf(';', at);
			}
			at++;
			found.add(descriptor.substring(start, at));
		}
		return found;
	}

	/** A BEFORE hook: its call, and its value returned unless it is the pass mark. */
	private void before(Hooks.Hook hook) {
		call(hook);
		u1(DUP);
		property(Bridge.PASS);
		int branch = length;
		u1(IF_ACMPEQ);
		u2(0);
		returnValue();
		int pass = length;
		code[branch + 1] = (byte) ((pass - branch) >> 8);
		code[branch + 2] = (byte) (pass - branch);
		frames.add(pass);
		u1(POP);
	}

	/** System.getProperties().get(key), on the stack. */
	private void property(String key) {
		u1(INVOKESTATIC);
		u2(file.methodRef("java/lang/System", "getProperties", "()Ljava/util/Properties;"));
		u1(LDC_W);
		u2(file.string(key));
		u1(INVOKEVIRTUAL);
		u2(file.methodRef("java/util/Properties", "get", "(Ljava/lang/Object;)Ljava/lang/Object;"));
	}

	/** The bridge's apply(the hook's name, [the hooked class, this or null, the arguments boxed]): its value on the stack. */
	private void call(Hooks.Hook hook) {
		property(Bridge.HOOKS);
		u1(CHECKCAST);
		u2(file.classRef(FUNCTION));
		u1(LDC_W);
		u2(file.string(hook.id()));
		number(parameters.size() + 2);
		u1(ANEWARRAY);
		u2(file.classRef(OBJECT));
		u1(DUP);
		number(0);
		u1(LDC_W);
		u2(file.thisClass);
		u1(AASTORE);
		u1(DUP);
		number(1);
		if (statics) {
			u1(ACONST_NULL);
		} else {
			load("L", 0);
		}
		u1(AASTORE);
		int slot = statics ? 0 : 1;
		for (int i = 0; i < parameters.size(); i++) {
			String parameter = parameters.get(i);
			u1(DUP);
			number(i + 2);
			load(parameter, slot);
			box(parameter);
			u1(AASTORE);
			slot += size(parameter);
		}
		u1(INVOKEINTERFACE);
		u2(file.interfaceMethodRef(FUNCTION, "apply", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;"));
		u1(3);
		u1(0);
	}

	/** The original, renamed, called with the wrapper's own arguments. */
	private void original(String owner, String renamed, String descriptor) {
		int slot = 0;
		if (!statics) {
			load("L", 0);
			slot = 1;
		}
		for (String parameter : parameters) {
			load(parameter, slot);
			slot += size(parameter);
		}
		u1(statics ? INVOKESTATIC : INVOKESPECIAL);
		u2(file.methodRef(owner, renamed, descriptor));
	}

	/** A BEFORE hook's value, an Object on the stack, returned as the method returns its type. */
	private void returnValue() {
		switch (returned.charAt(0)) {
			case 'V':
				u1(POP);
				break;
			case 'L':
				cast(returned.substring(1, returned.length() - 1));
				break;
			case '[':
				cast(returned);
				break;
			default:
				String boxed = boxOf(returned);
				cast(boxed);
				u1(INVOKEVIRTUAL);
				u2(file.methodRef(boxed, primitiveName(returned) + "Value", "()" + returned));
		}
		returnAs(returned);
	}

	private void cast(String internalName) {
		u1(CHECKCAST);
		u2(file.classRef(internalName));
	}

	private void returnAs(String type) {
		switch (type.charAt(0)) {
			case 'V':
				u1(RETURN);
				break;
			case 'J':
				u1(LRETURN);
				break;
			case 'F':
				u1(FRETURN);
				break;
			case 'D':
				u1(DRETURN);
				break;
			case 'L':
			case '[':
				u1(ARETURN);
				break;
			default:
				u1(IRETURN);
		}
	}

	private void load(String type, int slot) {
		if (slot > 0xFF) {
			throw new IllegalArgumentException("a method with more locals than the wrapper loads (" + slot + ")");
		}
		switch (type.charAt(0)) {
			case 'J':
				u1(LLOAD);
				break;
			case 'F':
				u1(FLOAD);
				break;
			case 'D':
				u1(DLOAD);
				break;
			case 'L':
			case '[':
				u1(ALOAD);
				break;
			default:
				u1(ILOAD);
		}
		u1(slot);
	}

	private void box(String type) {
		if (type.charAt(0) == 'L' || type.charAt(0) == '[') {
			return;
		}
		String boxed = boxOf(type);
		u1(INVOKESTATIC);
		u2(file.methodRef(boxed, "valueOf", "(" + type + ")L" + boxed + ";"));
	}

	private void number(int value) {
		if (value <= 5) {
			u1(ICONST_0 + value);
		} else if (value <= 0x7F) {
			u1(BIPUSH);
			u1(value);
		} else {
			u1(SIPUSH);
			u2(value);
		}
	}

	private static int size(String type) {
		return type.equals("J") || type.equals("D") ? 2 : 1;
	}

	private static String boxOf(String primitive) {
		switch (primitive) {
			case "Z":
				return "java/lang/Boolean";
			case "B":
				return "java/lang/Byte";
			case "C":
				return "java/lang/Character";
			case "S":
				return "java/lang/Short";
			case "I":
				return "java/lang/Integer";
			case "J":
				return "java/lang/Long";
			case "F":
				return "java/lang/Float";
			case "D":
				return "java/lang/Double";
			default:
				throw new IllegalArgumentException("no box for " + primitive);
		}
	}

	private static String primitiveName(String primitive) {
		switch (primitive) {
			case "Z":
				return "boolean";
			case "B":
				return "byte";
			case "C":
				return "char";
			case "S":
				return "short";
			case "I":
				return "int";
			case "J":
				return "long";
			case "F":
				return "float";
			case "D":
				return "double";
			default:
				throw new IllegalArgumentException("not a primitive: " + primitive);
		}
	}

	/** The Code attribute's body: its stack and locals, the code, no exception table, and its stack map frames. */
	private byte[] codeAttribute() {
		int words = statics ? 0 : 1;
		for (String parameter : parameters) {
			words += size(parameter);
		}
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		try {
			DataOutputStream out = new DataOutputStream(bytes);
			// a hook's call is 7 words deep at most (its array, an index and a long), over a returned long's 2
			out.writeShort(Math.max(9, words + 1));
			out.writeShort(words);
			out.writeInt(length);
			out.write(code, 0, length);
			out.writeShort(0);
			if (frames.isEmpty()) {
				out.writeShort(0);
			} else {
				out.writeShort(1);
				out.writeShort(file.utf8("StackMapTable"));
				byte[] table = stackMapTable();
				out.writeInt(table.length);
				out.write(table);
			}
		} catch (IOException e) {
			throw new IllegalStateException(e);
		}
		return bytes.toByteArray();
	}

	/** One frame at each BEFORE hook's "go on": the method's own locals, its hook's value on the stack. */
	private byte[] stackMapTable() throws IOException {
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		DataOutputStream out = new DataOutputStream(bytes);
		out.writeShort(frames.size());
		int previous = -1;
		for (int offset : frames) {
			int delta = offset - previous - 1;
			if (delta < 64) {
				out.writeByte(SAME_LOCALS_1_STACK_ITEM + delta);
			} else {
				out.writeByte(SAME_LOCALS_1_STACK_ITEM_EXTENDED);
				out.writeShort(delta);
			}
			out.writeByte(ITEM_OBJECT);
			out.writeShort(file.classRef(OBJECT));
			previous = offset;
		}
		return bytes.toByteArray();
	}

	private void u1(int value) {
		code[length++] = (byte) value;
	}

	private void u2(int value) {
		code[length++] = (byte) (value >> 8);
		code[length++] = (byte) value;
	}
}
