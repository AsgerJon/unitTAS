package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.SharedConstants;
import net.minecraft.client.GuiMessageTag;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.commands.CommandSource;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.TagParser;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ClientboundSetCarriedItemPacket;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.MobSpawnType;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ClickType;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.block.state.properties.Property;
import org.lwjgl.glfw.GLFW;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

/**
 * What 1.20.1 does its own way, for the probe's code shared by the versions (agent/src/modern/java; SPEC.md 19.7 step
 * 6c): the same methods as every version's Version, compiled with the shared code against 1.20.1's classes (in
 * Mojang's names, from its stubs; renamed to the obfuscated ones as the probe loads). 1.20.1 keeps its screen on
 * Minecraft and its HUD's hiding in the options, has ResourceLocation for ids, GLFW for input, plain NBT for an
 * entity's data, and names a click's mode ClickType.
 */
final class Version {

	private Version() {
	}

	// ---------------------------------------------------------------- the game

	/** The probe's port, as its hello says it. */
	static String port() {
		return "1.20.1";
	}

	/** The game's version, as it says itself. */
	static String minecraft() {
		return SharedConstants.getCurrentVersion().getName();
	}

	/** The version's own operations, which differ too widely to share: the view and the looks. */
	static void bindOwn(Probe probe) {
		V1_20_1View.bind(probe);
		V1_20_1Looks.bind(probe);
	}

	/** The version's worlds: the core's WorldOps on its calls. */
	static GameWorlds worlds() {
		return new V1_20_1Worlds();
	}

	/** The running world's folder's name; null when none is open. */
	static String worldFolder(MinecraftServer server) {
		return V1_20_1Worlds.folder(server);
	}

	/**
	 * A chat line's kind from the hooked addMessage's arguments (the line, its signature, its tag): the game's
	 * (system: its own tag, which addMessage(Component) gives), or a player's (chat: no tag, or a chat tag).
	 */
	static String chatKind(Object[] arguments) {
		Object tag = arguments[2];
		return tag == GuiMessageTag.system() || tag == GuiMessageTag.systemSinglePlayer() ? "system" : "chat";
	}

	/**
	 * The version's own hooks, which the shared entry passes on (its hooks file's view.frame and view.compiled: the
	 * view's frame and its sections' builds, which 1.20.1 keeps no state of). A BEFORE hook: the pass mark goes on.
	 */
	static Object hook(String id, Object self, Object[] arguments, Object pass) {
		switch (id) {
			case "view.frame":
				V1_20_1View.frame(arguments);
				return pass;
			case "view.compiled":
				V1_20_1View.compiled(arguments[0]);
				return pass;
			default:
				throw new IllegalArgumentException("the probe knows no hook " + id);
		}
	}

	// ---------------------------------------------------------------- screens and the HUD

	static Screen screen() {
		return Minecraft.getInstance().screen;
	}

	static void setScreen(Screen screen) {
		Minecraft.getInstance().setScreen(screen);
	}

	/** Whether a loading overlay is up (the game's start, a resource reload). */
	static boolean loading() {
		return Minecraft.getInstance().getOverlay() != null;
	}

	static ChatComponent chat() {
		return Minecraft.getInstance().gui.getChat();
	}

	static boolean hudHidden() {
		return Minecraft.getInstance().options.hideGui;
	}

	/** The HUD hidden if shown, shown if hidden (F1's: the options' hideGui). */
	static void toggleHud() {
		Minecraft mc = Minecraft.getInstance();
		mc.options.hideGui = !mc.options.hideGui;
	}

	/** The chat screen, opened with that text in its box. */
	static ChatScreen chatScreen(String text) {
		return new ChatScreen(text);
	}

	/** Whether the window holds the pointer (GLFW's cursor disabled, which the game's grab sets). */
	static boolean pointerGrabbed() {
		return GLFW.glfwGetInputMode(Minecraft.getInstance().getWindow().getWindow(), GLFW.GLFW_CURSOR)
			== GLFW.GLFW_CURSOR_DISABLED;
	}

	/** The frame as the screen shows it; 1.20.1 reads it at once, on the client thread. */
	static void screenshot(Consumer<NativeImage> taken) {
		taken.accept(Screenshot.takeScreenshot(Minecraft.getInstance().getMainRenderTarget()));
	}

	// ---------------------------------------------------------------- ids

	/** A key's id as text (minecraft:overworld). */
	static String id(ResourceKey<?> key) {
		return key.location().toString();
	}

	/** The registry's entry by its id; empty for an id it hasn't, or text that is no id. */
	static <T> Optional<T> byId(Registry<T> registry, String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? Optional.empty() : registry.getOptional(key);
	}

	/** Whether the registry has the id (a defaulted one, the blocks', answers its default for any other). */
	static boolean known(Registry<?> registry, String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key != null && registry.containsKey(key);
	}

	/** A key in the registry by its id; null for text that is no id. */
	static <T> ResourceKey<T> key(ResourceKey<? extends Registry<T>> registry, String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? null : ResourceKey.create(registry, key);
	}

	// ---------------------------------------------------------------- sounds

	/** A sound by its id, as a UI sound plays it; null for text that is no id. */
	static SoundEvent soundEvent(String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? null : SoundEvent.createVariableRangeEvent(key);
	}

	static String soundId(SoundInstance sound) {
		return sound.getLocation().toString();
	}

	/**
	 * Whether the game has the sound, the sound resolved so its volume and pitch read. 1.20.1's resolve picks a variant
	 * at random each time, so the probe hears a sound after the engine played it (its sound.play hook is AFTER) and
	 * resolves it only where the engine didn't (no sound engine loaded), when that changes nothing it played.
	 */
	static boolean soundKnown(SoundInstance sound, SoundManager manager) {
		if (sound.getSound() == null) {
			sound.resolve(manager);
		}
		return manager.getSoundEvent(sound.getLocation()) != null;
	}

	// ---------------------------------------------------------------- the inventory

	/** The main slots: the hotbar's nine, then the rest. */
	static List<ItemStack> mainItems(Inventory inventory) {
		return inventory.items;
	}

	static int selectedSlot(Inventory inventory) {
		return inventory.selected;
	}

	static void selectSlot(Inventory inventory, int slot) {
		inventory.selected = slot;
	}

	static ItemStack selectedItem(Inventory inventory) {
		return inventory.getSelected();
	}

	/** The game's own pick of what the crosshair meets, made afresh for the look as it is now (GameRenderer's). */
	static void pick(float partialTick) {
		Minecraft.getInstance().gameRenderer.pick(partialTick);
	}

	// ---------------------------------------------------------------- items' data, chat, reach, results

	/** An item's own data as the protocol has it: its NBT as SNBT ("nbt"), when it has any (components are 1.20.5's). */
	static void itemData(ItemStack stack, HolderLookup.Provider registries, JsonObject item) {
		CompoundTag tag = stack.getTag();
		if (tag != null && !tag.isEmpty()) {
			item.addProperty("nbt", tag.toString());
		}
	}

	/**
	 * The protocol's item's data put on its stack: its NBT (SNBT), as /give reads it; BadRequest for components, which
	 * 1.20.1's items haven't (data components from 1.20.5), and for SNBT that isn't a compound.
	 */
	static void applyItemData(ItemStack stack, JsonObject given, String id, HolderLookup.Provider registries)
		throws ProbeException {
		if (given.has("components")) {
			throw ProbeException.badRequest("item", port() + "'s items have NBT, not components (1.20.5's)");
		}
		String nbt = Json.string(given, "nbt");
		if (nbt != null) {
			stack.setTag(ModernValues.compound(nbt, "nbt"));
		}
	}

	/** A chat line as the game's own JSON. */
	static String chatJson(Component message) {
		return Component.Serializer.toJson(message);
	}

	/**
	 * How far the player reaches a block: its game mode's pick range (4.5; 5 in creative), as 1.20.1's pick takes it.
	 * The player is the client's own, whose game mode it is.
	 */
	static double blockReach(Player player) {
		return Minecraft.getInstance().gameMode.getPickRange();
	}

	/**
	 * How far the player reaches an entity, as 1.20.1's pick takes it: 3 blocks, or in creative (its far pick range) as
	 * far as the block pick reaches, where its ray ends.
	 */
	static double entityReach(Player player) {
		MultiPlayerGameMode mode = Minecraft.getInstance().gameMode;
		return mode.hasFarPickRange() ? mode.getPickRange() : 3.0;
	}

	/** The source, its command's result kept in result[0] as the command ends. */
	static CommandSourceStack withResult(CommandSourceStack source, int[] result) {
		return source.withCallback((context, success, value) -> result[0] = value);
	}

	/** A block entity's data, without its id and place, as /data reads it. */
	static CompoundTag tileData(BlockEntity tile, HolderLookup.Provider registries) {
		return tile.saveWithoutMetadata();
	}

	/** A mob effect's id (minecraft:speed). */
	static String effectId(MobEffectInstance effect) {
		return BuiltInRegistries.MOB_EFFECT.getKey(effect.getEffect()).toString();
	}

	/** A trapdoor's kind, whose hand-opening it says (a private field: 1.20.1 has no getter for it). */
	static BlockSetType trapdoorType(TrapDoorBlock block) {
		return Members.get(Trapdoors.TYPE, block);
	}

	/** Found at the first trapdoor asked about, once the probe has its names. */
	private static final class Trapdoors {

		static final java.lang.reflect.Field TYPE = Members.field(TrapDoorBlock.class, "type");
	}

	// ---------------------------------------------------------------- the world, players and entities

	/** The lowest block a level has. */
	static int minY(Level level) {
		return level.getMinBuildHeight();
	}

	static ServerLevel level(ServerPlayer player) {
		return player.serverLevel();
	}

	/** A player to another place, in that level, looking that way, nothing else changed. */
	static void teleport(ServerPlayer player, ServerLevel to, double x, double y, double z, float yaw, float pitch) {
		player.teleportTo(to, x, y, z, yaw, pitch);
	}

	/** No bed or anchor to respawn at. */
	static void clearRespawn(ServerPlayer player) {
		player.setRespawnPosition(Level.OVERWORLD, null, 0.0F, false, false);
	}

	/** The held slot told to the player's client. */
	static void sendHeldSlot(ServerPlayer player, int slot) {
		player.connection.send(new ClientboundSetCarriedItemPacket(slot));
	}

	/** What hears a command's lines for a player: the player itself. */
	static CommandSource commandSource(ServerPlayer player) {
		return player;
	}

	/** An entity's data, without its id, as /data reads it. */
	static CompoundTag save(Entity entity, HolderLookup.Provider registries) {
		return entity.saveWithoutId(new CompoundTag());
	}

	static void load(Entity entity, CompoundTag data, HolderLookup.Provider registries) {
		entity.load(data);
	}

	static void loadTile(BlockEntity tile, CompoundTag data, HolderLookup.Provider registries) {
		tile.load(data);
	}

	/** An entity made as a command makes one; null for a kind a command can't make. */
	static Entity create(EntityType<?> kind, ServerLevel level) {
		return kind.create(level);
	}

	/** A mob given what it would have spawned with, as /summon does. */
	static void finalizeSpawn(Mob mob, ServerLevel level) {
		mob.finalizeSpawn(level, level.getCurrentDifficultyAt(mob.blockPosition()), MobSpawnType.COMMAND, null, null);
	}

	/** An entity put at a place, looking that way, before it is in a world. */
	static void place(Entity entity, double x, double y, double z, float yaw, float pitch) {
		entity.moveTo(x, y, z, yaw, pitch);
	}

	/** A block's state from text, as commands read it (minecraft:oak_stairs[facing=east]). */
	static BlockState parseBlock(String text) throws CommandSyntaxException {
		return BlockStateParser.parseForBlock(BuiltInRegistries.BLOCK.asLookup(), text, false).blockState();
	}

	/** A compound from SNBT, as the game's own commands read it. */
	static CompoundTag parseCompound(String text) throws CommandSyntaxException {
		return TagParser.parseTag(text);
	}

	/** Each of a state's properties, by its name and its value's name. */
	static void properties(BlockState state, BiConsumer<String, String> each) {
		for (Map.Entry<Property<?>, Comparable<?>> value : state.getValues().entrySet()) {
			each.accept(value.getKey().getName(), valueName(value.getKey(), value.getValue()));
		}
	}

	@SuppressWarnings("unchecked")
	private static <T extends Comparable<T>> String valueName(Property<T> property, Comparable<?> value) {
		return property.getName((T) value);
	}

	// ---------------------------------------------------------------- input

	/** A raw key by its code: GLFW's key code. */
	static InputConstants.Key rawKey(int code) {
		return InputConstants.Type.KEYSYM.getOrCreate(code);
	}

	/** A binding by its name (key.jump); null for none. KeyMapping's map of them is private in 1.20.1. */
	static KeyMapping binding(String name) {
		Map<String, KeyMapping> all = Members.get(Bindings.ALL, null);
		return all.get(name);
	}

	/** Found at the first binding asked for, once the probe has its names (a Version is used before that). */
	private static final class Bindings {

		static final java.lang.reflect.Field ALL = Members.field(KeyMapping.class, "ALL");
	}

	/** A screen given a character, as GLFW gives one. */
	static void charTyped(Screen screen, int character) {
		screen.charTyped((char) character, 0);
	}

	/** A screen given a key, as GLFW gives one: its key code and its scancode. */
	static void keyPressed(Screen screen, int key, int scancode) {
		screen.keyPressed(key, scancode, 0);
	}

	/**
	 * A key by its portable name, as a screen is given it: [its GLFW key code, its scancode (the platform's, as GLFW
	 * says it), the character it types or 0]; null for a name not known.
	 */
	static int[] portableKey(String name) {
		if (name.length() == 1) {
			char c = name.charAt(0);
			if (c >= 'a' && c <= 'z') {
				return glfw(InputConstants.KEY_A + (c - 'a'), c);
			}
			if (c >= '1' && c <= '9') {
				return glfw(InputConstants.KEY_1 + (c - '1'), c);
			}
			if (c == '0') {
				return glfw(InputConstants.KEY_0, c);
			}
			return null;
		}
		switch (name) {
			case "space": return glfw(InputConstants.KEY_SPACE, ' ');
			case "enter": return glfw(InputConstants.KEY_RETURN, 0);
			case "escape": return glfw(InputConstants.KEY_ESCAPE, 0);
			case "tab": return glfw(InputConstants.KEY_TAB, 0);
			case "backspace": return glfw(InputConstants.KEY_BACKSPACE, 0);
			case "delete": return glfw(InputConstants.KEY_DELETE, 0);
			case "up": return glfw(InputConstants.KEY_UP, 0);
			case "down": return glfw(InputConstants.KEY_DOWN, 0);
			case "left": return glfw(InputConstants.KEY_LEFT, 0);
			case "right": return glfw(InputConstants.KEY_RIGHT, 0);
			case "home": return glfw(InputConstants.KEY_HOME, 0);
			case "end": return glfw(InputConstants.KEY_END, 0);
			case "page_up": return glfw(InputConstants.KEY_PAGEUP, 0);
			case "page_down": return glfw(InputConstants.KEY_PAGEDOWN, 0);
			default:
				break;
		}
		if (name.matches("f([1-9]|1[0-2])")) {
			return glfw(InputConstants.KEY_F1 + Integer.parseInt(name.substring(1)) - 1, 0);
		}
		return null;
	}

	private static int[] glfw(int key, int character) {
		return new int[] {key, GLFW.glfwGetKeyScancode(key), character};
	}

	// ---------------------------------------------------------------- containers

	/** container.click's modes, in 1.7.10's order (pickup, quick_move, swap, clone, throw, quick_craft, pickup_all). */
	static Object[] clickModes() {
		return ClickType.values();
	}

	/** The class of a click's mode, for the screen's own slotClicked. */
	static Class<?> clickModeClass() {
		return ClickType.class;
	}
}
