package io.github.asgerjon.unittas.agent.game;

import java.util.ArrayList;
import java.util.List;

/** Generics in its members' signatures, and the game's listeners called from its code. */
public class World {

	private final List<Entity> entities = new ArrayList<>();
	private final List<Listener> listeners = new ArrayList<>();

	public List<Entity> entities() {
		return entities;
	}

	public void add(Entity entity) {
		entities.add(entity);
		for (Listener listener : listeners) {
			listener.heard(entity);
		}
	}

	public void listen(Listener listener) {
		listeners.add(listener);
	}

	public <T extends Entity> T first(Class<T> type) {
		for (Entity entity : entities) {
			if (type.isInstance(entity)) {
				return type.cast(entity);
			}
		}
		return null;
	}
}
