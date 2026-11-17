package io.github.asgerjon.unittas.agent;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * A class file as the rewriter needs it (SPEC.md 19.7 step 6a; the format is JVMS chapter 4): its constant pool read
 * entry by entry, so that new entries can follow the old ones; its methods by their access, name, descriptor and
 * attributes; every other part kept as the bytes it was. Written back, every old entry keeps its index, so all that
 * names one (the fields, the code, the attributes) stays exactly as it was. JDK only, on any Java the agent runs on.
 */
final class ClassBytes {

	static final int PUBLIC = 0x0001;
	static final int PRIVATE = 0x0002;
	static final int PROTECTED = 0x0004;
	static final int STATIC = 0x0008;
	static final int NATIVE = 0x0100;
	static final int INTERFACE = 0x0200;
	static final int ABSTRACT = 0x0400;
	static final int SYNTHETIC = 0x1000;

	private static final int UTF8 = 1;
	private static final int INTEGER = 3;
	private static final int FLOAT = 4;
	private static final int LONG = 5;
	private static final int DOUBLE = 6;
	private static final int CLASS = 7;
	private static final int STRING = 8;
	private static final int FIELD = 9;
	private static final int METHOD = 10;
	private static final int INTERFACE_METHOD = 11;
	private static final int NAME_AND_TYPE = 12;
	private static final int METHOD_HANDLE = 15;
	private static final int METHOD_TYPE = 16;
	private static final int DYNAMIC = 17;
	private static final int INVOKE_DYNAMIC = 18;
	private static final int MODULE = 19;
	private static final int PACKAGE = 20;

	/** One method: what the rewriter reads and changes of it, its attributes as they were. */
	static final class Method {

		int access;
		int name;
		int descriptor;
		final List<Attribute> attributes;

		Method(int access, int name, int descriptor, List<Attribute> attributes) {
			this.access = access;
			this.name = name;
			this.descriptor = descriptor;
			this.attributes = attributes;
		}
	}

	/** An attribute: its name's entry and its body, as the file had them. */
	record Attribute(int name, byte[] body) {
	}

	private final int minor;
	private final int major;
	/** Each entry's bytes, its tag first, at its index: none at 0 nor after a long or a double (JVMS 4.4.5). */
	private final List<byte[]> pool = new ArrayList<>();
	/** The entries added, by what they are, so each is added once. */
	private final Map<String, Integer> added = new HashMap<>();
	final int access;
	final int thisClass;
	private final int superClass;
	private final byte[] interfaces;
	private final byte[] fields;
	final List<Method> methods = new ArrayList<>();
	private final byte[] attributes;

	ClassBytes(byte[] bytes) throws IOException {
		DataInputStream in = new DataInputStream(new ByteArrayInputStream(bytes));
		if (in.readInt() != 0xCAFEBABE) {
			throw new IllegalArgumentException("not a class file");
		}
		minor = in.readUnsignedShort();
		major = in.readUnsignedShort();
		int count = in.readUnsignedShort();
		pool.add(null);
		for (int index = 1; index < count; index++) {
			int tag = in.readUnsignedByte();
			int size;
			switch (tag) {
				case UTF8:
					size = 2 + peekShort(in);
					break;
				case INTEGER:
				case FLOAT:
				case FIELD:
				case METHOD:
				case INTERFACE_METHOD:
				case NAME_AND_TYPE:
				case DYNAMIC:
				case INVOKE_DYNAMIC:
					size = 4;
					break;
				case LONG:
				case DOUBLE:
					size = 8;
					break;
				case CLASS:
				case STRING:
				case METHOD_TYPE:
				case MODULE:
				case PACKAGE:
					size = 2;
					break;
				case METHOD_HANDLE:
					size = 3;
					break;
				default:
					throw new IllegalArgumentException("an unknown constant pool tag " + tag + " at entry " + index);
			}
			byte[] entry = new byte[1 + size];
			entry[0] = (byte) tag;
			in.readFully(entry, 1, size);
			pool.add(entry);
			if (tag == LONG || tag == DOUBLE) {
				pool.add(null);
				index++;
			}
		}
		access = in.readUnsignedShort();
		thisClass = in.readUnsignedShort();
		superClass = in.readUnsignedShort();
		ByteArrayOutputStream kept = new ByteArrayOutputStream();
		DataOutputStream out = new DataOutputStream(kept);
		int names = in.readUnsignedShort();
		out.writeShort(names);
		copy(in, out, 2 * names);
		interfaces = kept.toByteArray();
		kept.reset();
		int fieldCount = in.readUnsignedShort();
		out.writeShort(fieldCount);
		for (int i = 0; i < fieldCount; i++) {
			copy(in, out, 6);
			copyAttributes(in, out);
		}
		fields = kept.toByteArray();
		int methodCount = in.readUnsignedShort();
		for (int i = 0; i < methodCount; i++) {
			int flags = in.readUnsignedShort();
			int name = in.readUnsignedShort();
			int descriptor = in.readUnsignedShort();
			List<Attribute> its = new ArrayList<>();
			int attributeCount = in.readUnsignedShort();
			for (int j = 0; j < attributeCount; j++) {
				int attributeName = in.readUnsignedShort();
				byte[] body = new byte[in.readInt()];
				in.readFully(body);
				its.add(new Attribute(attributeName, body));
			}
			methods.add(new Method(flags, name, descriptor, its));
		}
		kept.reset();
		copyAttributes(in, out);
		attributes = kept.toByteArray();
		if (in.read() != -1) {
			throw new IllegalArgumentException("bytes after the class file's end");
		}
	}

	/** A Utf8 entry's text. */
	String utf8(int index) {
		byte[] entry = entry(index, UTF8);
		try {
			return new DataInputStream(new ByteArrayInputStream(entry, 1, entry.length - 1)).readUTF();
		} catch (IOException e) {
			throw new IllegalArgumentException("entry " + index + " isn't modified UTF-8", e);
		}
	}

	/** A Class entry's name (java/lang/Object). */
	String className(int index) {
		byte[] entry = entry(index, CLASS);
		return utf8(((entry[1] & 0xFF) << 8) | (entry[2] & 0xFF));
	}

	/** The class's own name. */
	String name() {
		return className(thisClass);
	}

	int utf8(String text) {
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		try {
			DataOutputStream out = new DataOutputStream(bytes);
			out.writeByte(UTF8);
			out.writeUTF(text);
		} catch (IOException e) {
			throw new IllegalStateException(e);
		}
		return add("utf8 " + text, bytes.toByteArray());
	}

	int classRef(String internalName) {
		return add("class " + internalName, CLASS, utf8(internalName));
	}

	int string(String text) {
		return add("string " + text, STRING, utf8(text));
	}

	int methodRef(String owner, String name, String descriptor) {
		return add("method " + owner + "." + name + descriptor, METHOD, classRef(owner), nameAndType(name, descriptor));
	}

	int interfaceMethodRef(String owner, String name, String descriptor) {
		return add("interface method " + owner + "." + name + descriptor, INTERFACE_METHOD, classRef(owner),
			nameAndType(name, descriptor));
	}

	private int nameAndType(String name, String descriptor) {
		return add("name and type " + name + descriptor, NAME_AND_TYPE, utf8(name), utf8(descriptor));
	}

	/** The class file again, the new entries after the old ones. */
	byte[] bytes() {
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		try {
			DataOutputStream out = new DataOutputStream(bytes);
			out.writeInt(0xCAFEBABE);
			out.writeShort(minor);
			out.writeShort(major);
			out.writeShort(pool.size());
			for (byte[] entry : pool) {
				if (entry != null) {
					out.write(entry);
				}
			}
			out.writeShort(access);
			out.writeShort(thisClass);
			out.writeShort(superClass);
			out.write(interfaces);
			out.write(fields);
			out.writeShort(methods.size());
			for (Method method : methods) {
				out.writeShort(method.access);
				out.writeShort(method.name);
				out.writeShort(method.descriptor);
				out.writeShort(method.attributes.size());
				for (Attribute attribute : method.attributes) {
					out.writeShort(attribute.name());
					out.writeInt(attribute.body().length);
					out.write(attribute.body());
				}
			}
			out.write(attributes);
		} catch (IOException e) {
			throw new IllegalStateException(e);
		}
		return bytes.toByteArray();
	}

	private byte[] entry(int index, int tag) {
		byte[] entry = index > 0 && index < pool.size() ? pool.get(index) : null;
		if (entry == null || entry[0] != tag) {
			throw new IllegalArgumentException("entry " + index + " isn't of tag " + tag);
		}
		return entry;
	}

	private int add(String key, int tag, int... references) {
		byte[] entry = new byte[1 + 2 * references.length];
		entry[0] = (byte) tag;
		for (int i = 0; i < references.length; i++) {
			entry[1 + 2 * i] = (byte) (references[i] >> 8);
			entry[2 + 2 * i] = (byte) references[i];
		}
		return add(key, entry);
	}

	private int add(String key, byte[] entry) {
		Integer known = added.get(key);
		if (known != null) {
			return known;
		}
		if (pool.size() >= 0xFFFF) {
			throw new IllegalArgumentException("the constant pool is full");
		}
		pool.add(entry);
		added.put(key, pool.size() - 1);
		return pool.size() - 1;
	}

	private static int peekShort(DataInputStream in) throws IOException {
		in.mark(2);
		int value = in.readUnsignedShort();
		in.reset();
		return value;
	}

	private static void copy(DataInputStream in, DataOutputStream out, int size) throws IOException {
		byte[] bytes = new byte[size];
		in.readFully(bytes);
		out.write(bytes);
	}

	private static void copyAttributes(DataInputStream in, DataOutputStream out) throws IOException {
		int count = in.readUnsignedShort();
		out.writeShort(count);
		for (int i = 0; i < count; i++) {
			out.writeShort(in.readUnsignedShort());
			int length = in.readInt();
			out.writeInt(length);
			copy(in, out, length);
		}
	}
}
