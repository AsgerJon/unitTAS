package io.github.asgerjon.unittas.agent;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * A class file renamed by a table of names (SPEC.md 19.7 step 6b), two ways:
 * - the probe's, as it loads (new Renamer): written and compiled in Mojang's names, renamed to the ones the game runs
 *   under. Its classes' names, every member it reaches (each by the class that declares it, which the builder found:
 *   the declarers, owner NAME DESCRIPTOR to the declaring class, or "-" where no class of the game declares it),
 *   its own methods that override the game's, a lambda's method for the game's own interface, and every descriptor
 *   and signature. A game member it can't name, by the table or the declarers, is refused, never passed on as it is;
 * - a game class as a stub (stubs()), from the running names back to Mojang's: its declarations alone, for javac to
 *   compile a port against: its name, supertypes, fields and methods (but the synthetic) with their signatures,
 *   checked exceptions, constants and nested classes; its code and the rest dropped. A member the table hasn't keeps
 *   its running name there (a stub is never run).
 * Entries are replaced where they are, so the code, which names them by index, needs no change. JDK only.
 */
final class Renamer {

	/** The bootstrap methods whose call site names the method of the interface it makes (a lambda's). */
	private static final String LAMBDAS = "java/lang/invoke/LambdaMetafactory";
	private static final Set<String> STUB_CLASS_ATTRIBUTES = Set.of("Signature", "InnerClasses");
	private static final Set<String> STUB_MEMBER_ATTRIBUTES = Set.of("Signature", "Exceptions", "ConstantValue");

	private final Names names;
	private final Map<String, String> declarers;
	private final boolean stubs;

	/** The probe's renamer: its declarers as the builder found them. */
	Renamer(Names names, Map<String, String> declarers) {
		this(names, declarers, false);
	}

	private Renamer(Names names, Map<String, String> declarers, boolean stubs) {
		this.names = names;
		this.declarers = declarers;
		this.stubs = stubs;
	}

	/** The stubs' renamer: the game's classes, from their running names back to Mojang's (names.inverse()). */
	static Renamer stubs(Names inverse) {
		return new Renamer(inverse, Map.of(), true);
	}

	byte[] rename(byte[] bytes) throws IOException {
		ClassBytes file = new ClassBytes(bytes);
		String self = file.name();
		boolean game = names.known(self);
		// everything read by the names it had, before an entry is replaced
		int size = file.poolSize();
		String[] classNames = new String[size];
		int[][] members = new int[size][];
		String[][] memberNames = new String[size][];
		for (int index = 1; index < size; index++) {
			int tag = file.tag(index);
			if (tag == ClassBytes.CLASS) {
				classNames[index] = file.className(index);
			} else if (tag == ClassBytes.FIELD || tag == ClassBytes.METHOD || tag == ClassBytes.INTERFACE_METHOD) {
				int owner = file.reference(index, 0);
				int nameAndType = file.reference(index, 1);
				memberNames[index] = new String[] {file.className(owner), file.utf8(file.reference(nameAndType, 0)),
					file.utf8(file.reference(nameAndType, 1))};
				members[index] = new int[] {owner};
			} else if (tag == ClassBytes.INVOKE_DYNAMIC || tag == ClassBytes.DYNAMIC) {
				int nameAndType = file.reference(index, 1);
				memberNames[index] = new String[] {"", file.utf8(file.reference(nameAndType, 0)),
					file.utf8(file.reference(nameAndType, 1))};
				members[index] = new int[] {file.reference(index, 0)};
			} else if (tag == ClassBytes.METHOD_TYPE) {
				memberNames[index] = new String[] {"", "", file.utf8(file.reference(index, 0))};
			}
		}
		List<int[]> bootstraps = bootstrapMethods(file);
		renameMembers(file, self, game, file.fields, true);
		renameMembers(file, self, game, file.methods, false);
		renameAttributes(file, file.attributes, stubs ? STUB_CLASS_ATTRIBUTES : null, classNames);
		if (!stubs) {
			for (int index = 1; index < size; index++) {
				int tag = file.tag(index);
				String[] was = memberNames[index];
				if (tag == ClassBytes.FIELD || tag == ClassBytes.METHOD || tag == ClassBytes.INTERFACE_METHOD) {
					String name = reached(tag == ClassBytes.FIELD, was[0], was[1], was[2]);
					file.replace(index, tag, members[index][0], file.nameAndType(name, names.descriptor(was[2])));
				} else if (tag == ClassBytes.INVOKE_DYNAMIC || tag == ClassBytes.DYNAMIC) {
					String name = was[1];
					if (tag == ClassBytes.INVOKE_DYNAMIC) {
						name = lambdaMethod(file, bootstraps.get(members[index][0]), memberNames, was);
					}
					file.replace(index, tag, members[index][0], file.nameAndType(name, names.descriptor(was[2])));
				} else if (tag == ClassBytes.METHOD_TYPE) {
					file.replace(index, tag, file.utf8(names.descriptor(was[2])));
				}
			}
		}
		for (int index = 1; index < size; index++) {
			if (classNames[index] != null) {
				String renamed = names.typeName(classNames[index]);
				if (!renamed.equals(classNames[index])) {
					file.replace(index, ClassBytes.CLASS, file.utf8(renamed));
				}
			}
		}
		return file.bytes();
	}

	/** A member the class reaches, by its running name: the one its declaring class gives it, if that is the game's. */
	private String reached(boolean field, String owner, String name, String descriptor) {
		String declarer = declarers.get(Names.key(owner, name, descriptor));
		if (declarer == null) {
			if (!names.known(owner)) {
				return name;
			}
			// a member the builder didn't see: only the owner's own, by the table, is named
			declarer = owner;
		}
		if (declarer.equals("-")) {
			return name;
		}
		String running = field ? names.field(declarer, name, descriptor) : names.method(declarer, name, descriptor);
		if (running == null) {
			throw new IllegalArgumentException("no " + names.kind + " name for " + (field ? "the field " : "the method ")
				+ declarer + "." + name + descriptor + " (reached as " + owner + "'s)");
		}
		return running;
	}

	/** A lambda's call site names its interface's method: renamed if the interface is the game's. */
	private String lambdaMethod(ClassBytes file, int[] bootstrap, String[][] memberNames, String[] callSite) {
		String[] method = memberNames[file.reference(bootstrap[0], 0)];
		if (method == null || !method[0].equals(LAMBDAS) || bootstrap.length < 2) {
			return callSite[1];
		}
		String made = callSite[2].substring(callSite[2].indexOf(')') + 1);
		if (!made.startsWith("L")) {
			return callSite[1];
		}
		String face = made.substring(1, made.length() - 1);
		String[] erased = memberNames[bootstrap[1]];
		if (erased == null) {
			throw new IllegalArgumentException("a lambda's call site whose first argument isn't a method type");
		}
		return reached(false, face, callSite[1], erased[2]);
	}

	/** The class's fields' or methods' names and descriptors renamed, their attributes too. */
	private void renameMembers(ClassBytes file, String self, boolean game, List<ClassBytes.Member> members,
		boolean fields) throws IOException {
		List<ClassBytes.Member> dropped = new ArrayList<>();
		for (ClassBytes.Member member : members) {
			if (stubs && (member.access & ClassBytes.SYNTHETIC) != 0) {
				dropped.add(member);
				continue;
			}
			String name = file.utf8(member.name);
			String descriptor = file.utf8(member.descriptor);
			String running = name;
			if (game) {
				String found = fields ? names.field(self, name, descriptor) : names.method(self, name, descriptor);
				if (found != null) {
					running = found;
				} else if (!stubs) {
					throw new IllegalArgumentException("no " + names.kind + " name for " + self + "." + name + descriptor);
				}
			} else if (!fields && !name.startsWith("<")) {
				// the probe's own method: renamed with the game's that it overrides
				String declarer = declarers.get(Names.key(self, name, descriptor));
				if (declarer != null && !declarer.equals("-")) {
					running = reached(false, self, name, descriptor);
				}
			}
			if (!running.equals(name)) {
				member.name = file.utf8(running);
			}
			String renamed = names.descriptor(descriptor);
			if (!renamed.equals(descriptor)) {
				member.descriptor = file.utf8(renamed);
			}
			renameAttributes(file, member.attributes, stubs ? STUB_MEMBER_ATTRIBUTES : null, null);
		}
		members.removeAll(dropped);
	}

	/** Attributes renamed where they name classes; for a stub, only those it keeps. */
	private void renameAttributes(ClassBytes file, List<ClassBytes.Attribute> attributes, Set<String> kept,
		String[] classNames) throws IOException {
		List<ClassBytes.Attribute> out = new ArrayList<>();
		for (ClassBytes.Attribute attribute : attributes) {
			String name = file.utf8(attribute.name());
			if (kept != null && !kept.contains(name)) {
				continue;
			}
			switch (name) {
				case "Signature": {
					int index = u2(attribute.body(), 0);
					out.add(new ClassBytes.Attribute(attribute.name(),
						u2Bytes(file.utf8(names.signature(file.utf8(index))))));
					break;
				}
				case "InnerClasses":
					out.add(new ClassBytes.Attribute(attribute.name(), innerClasses(file, attribute.body(), classNames)));
					break;
				case "Code":
					refuseLocalNames(file, attribute.body());
					out.add(attribute);
					break;
				case "Record":
					out.add(new ClassBytes.Attribute(attribute.name(), record(file, attribute.body())));
					break;
				default:
					out.add(attribute);
			}
		}
		attributes.clear();
		attributes.addAll(out);
	}

	/** Each nested class's simple name, where the class is the game's, as its other name has it. */
	private byte[] innerClasses(ClassBytes file, byte[] body, String[] classNames) throws IOException {
		DataInputStream in = new DataInputStream(new ByteArrayInputStream(body));
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		DataOutputStream out = new DataOutputStream(bytes);
		int count = in.readUnsignedShort();
		out.writeShort(count);
		for (int i = 0; i < count; i++) {
			int inner = in.readUnsignedShort();
			int outer = in.readUnsignedShort();
			int simple = in.readUnsignedShort();
			int flags = in.readUnsignedShort();
			String innerName = classNames != null ? classNames[inner] : file.className(inner);
			if (simple != 0 && names.known(innerName)) {
				String running = names.className(innerName);
				simple = file.utf8(running.substring(running.lastIndexOf('$') + 1));
			}
			out.writeShort(inner);
			out.writeShort(outer);
			out.writeShort(simple);
			out.writeShort(flags);
		}
		return bytes.toByteArray();
	}

	/** A record's components' descriptors and signatures renamed (JVMS 4.7.30). */
	private byte[] record(ClassBytes file, byte[] body) throws IOException {
		DataInputStream in = new DataInputStream(new ByteArrayInputStream(body));
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		DataOutputStream out = new DataOutputStream(bytes);
		int count = in.readUnsignedShort();
		out.writeShort(count);
		for (int i = 0; i < count; i++) {
			out.writeShort(in.readUnsignedShort());
			out.writeShort(file.utf8(names.descriptor(file.utf8(in.readUnsignedShort()))));
			int attributes = in.readUnsignedShort();
			out.writeShort(attributes);
			for (int j = 0; j < attributes; j++) {
				int name = in.readUnsignedShort();
				byte[] its = new byte[in.readInt()];
				in.readFully(its);
				if (file.utf8(name).equals("Signature")) {
					its = u2Bytes(file.utf8(names.signature(file.utf8(u2(its, 0)))));
				}
				out.writeShort(name);
				out.writeInt(its.length);
				out.write(its);
			}
		}
		return bytes.toByteArray();
	}

	/** Local variables' tables name their types by descriptor, which the renamer doesn't follow: built without them. */
	private static void refuseLocalNames(ClassBytes file, byte[] code) throws IOException {
		DataInputStream in = new DataInputStream(new ByteArrayInputStream(code));
		in.skipBytes(4);
		in.skipBytes(in.readInt());
		in.skipBytes(8 * in.readUnsignedShort());
		int count = in.readUnsignedShort();
		for (int i = 0; i < count; i++) {
			String name = file.utf8(in.readUnsignedShort());
			if (name.equals("LocalVariableTable") || name.equals("LocalVariableTypeTable")) {
				throw new IllegalArgumentException(file.name() + " was compiled with its local variables' names (javac"
					+ " -g): the agent's probe is built without them");
			}
			in.skipBytes(in.readInt());
		}
	}

	/** The class's bootstrap methods: each its method handle's entry, then its arguments' entries. */
	private static List<int[]> bootstrapMethods(ClassBytes file) throws IOException {
		List<int[]> found = new ArrayList<>();
		for (ClassBytes.Attribute attribute : file.attributes) {
			if (!file.utf8(attribute.name()).equals("BootstrapMethods")) {
				continue;
			}
			DataInputStream in = new DataInputStream(new ByteArrayInputStream(attribute.body()));
			int count = in.readUnsignedShort();
			for (int i = 0; i < count; i++) {
				int handle = in.readUnsignedShort();
				int[] method = new int[1 + in.readUnsignedShort()];
				method[0] = handle;
				for (int j = 1; j < method.length; j++) {
					method[j] = in.readUnsignedShort();
				}
				found.add(method);
			}
		}
		return found;
	}

	private static int u2(byte[] bytes, int at) {
		return ((bytes[at] & 0xFF) << 8) | (bytes[at + 1] & 0xFF);
	}

	private static byte[] u2Bytes(int value) {
		return new byte[] {(byte) (value >> 8), (byte) value};
	}
}
